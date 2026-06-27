import io
import re
import shutil
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from app.core.config import settings


@dataclass
class OCRResult:
    text: str
    page_count: int
    used_ocr: bool
    confidence: float | None
    lines: list["OCRLine"]


@dataclass
class OCRLine:
    page_number: int
    line_number: int
    text: str
    confidence: float | None
    bbox: list[float] | None


def ocr_status() -> dict:
    executable = shutil.which("tesseract")
    languages: list[str] = []
    version = None
    if executable:
        try:
            version = str(pytesseract.get_tesseract_version()).splitlines()[0]
            languages = pytesseract.get_languages(config="")
        except pytesseract.TesseractError:
            pass
    requested = settings.ocr_languages.split("+")
    return {
        "enabled": settings.ocr_enabled,
        "available": bool(executable),
        "executable": executable,
        "version": version,
        "installed_languages": languages,
        "requested_languages": requested,
        "missing_languages": [item for item in requested if item not in languages],
        "dpi": settings.ocr_dpi,
    }


def _prepare_image(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("L")
    image = ImageOps.autocontrast(image)
    image = ImageEnhance.Contrast(image).enhance(1.5)
    return image.filter(ImageFilter.SHARPEN)


def _ocr_image(
    image: Image.Image, page_number: int = 1, page_segmentation_mode: int | None = None
) -> tuple[str, float | None, list[OCRLine]]:
    status = ocr_status()
    if not status["available"]:
        raise RuntimeError(
            "Tesseract OCR is not installed. Install Tesseract and the requested "
            "language packs, then restart the backend."
        )
    installed = set(status["installed_languages"])
    requested = [
        language
        for language in settings.ocr_languages.split("+")
        if language in installed
    ]
    language = "+".join(requested) or "eng"
    prepared = _prepare_image(image)
    config = (
        f"--oem 3 --psm "
        f"{page_segmentation_mode or settings.ocr_page_segmentation_mode}"
    )
    data = pytesseract.image_to_data(
        prepared,
        lang=language,
        config=config,
        output_type=pytesseract.Output.DICT,
    )
    lines: OrderedDict[tuple[int, int, int, int], list[dict]] = OrderedDict()
    confidences = []
    keys = zip(
        data["page_num"],
        data["block_num"],
        data["par_num"],
        data["line_num"],
        data["text"],
        data["conf"],
        data["left"],
        data["top"],
        data["width"],
        data["height"],
        strict=True,
    )
    for (
        page,
        block,
        paragraph,
        line,
        text,
        confidence,
        left,
        top,
        width,
        height,
    ) in keys:
        if text.strip():
            line_key = (page, block, paragraph, line)
            lines.setdefault(line_key, []).append(
                {
                    "text": text.strip(),
                    "confidence": confidence,
                    "left": int(left),
                    "top": int(top),
                    "right": int(left) + int(width),
                    "bottom": int(top) + int(height),
                }
            )
            try:
                numeric_confidence = float(confidence)
                if numeric_confidence >= 0:
                    confidences.append(numeric_confidence)
            except (TypeError, ValueError):
                continue
    structured_lines = []
    for line_number, words in enumerate(lines.values(), start=1):
        word_confidences = []
        for word in words:
            try:
                value = float(word["confidence"])
                if value >= 0:
                    word_confidences.append(value / 100)
            except (TypeError, ValueError):
                pass
        structured_lines.append(
            OCRLine(
                page_number=page_number,
                line_number=line_number,
                text=" ".join(str(word["text"]) for word in words),
                confidence=(
                    sum(word_confidences) / len(word_confidences)
                    if word_confidences
                    else None
                ),
                bbox=[
                    min(int(word["left"]) for word in words) / prepared.width * 100,
                    min(int(word["top"]) for word in words) / prepared.height * 100,
                    (
                        max(int(word["right"]) for word in words)
                        - min(int(word["left"]) for word in words)
                    )
                    / prepared.width
                    * 100,
                    (
                        max(int(word["bottom"]) for word in words)
                        - min(int(word["top"]) for word in words)
                    )
                    / prepared.height
                    * 100,
                ],
            )
        )
    text = "\n".join(item.text for item in structured_lines)
    confidence = sum(confidences) / len(confidences) / 100 if confidences else None
    return text, confidence, structured_lines


def extract_image(path: Path) -> OCRResult:
    with Image.open(path) as image:
        width, height = image.size
        page_segmentation_mode = 11 if height / max(width, 1) >= 1.8 else None
        text, confidence, lines = _ocr_image(
            image, page_segmentation_mode=page_segmentation_mode
        )
    return OCRResult(
        text=text,
        page_count=1,
        used_ocr=True,
        confidence=confidence,
        lines=lines,
    )


def extract_pdf(
    path: Path, force_ocr: bool = False, password: str | None = None
) -> OCRResult:
    with fitz.open(path) as pdf:
        if pdf.needs_pass:
            if not password:
                raise ValueError("This PDF is password protected.")
            if not pdf.authenticate(password):
                raise ValueError("The PDF password is incorrect.")
        native_pages = [page.get_text("text") for page in pdf]
        native_text = "\n\n".join(native_pages)
        fragmented_tokens = re.findall(
            r"(?:\b[\wÄÖÜäöüß]\s+){3,}[\wÄÖÜäöüß]\b", native_text
        )
        fragmented_ratio = sum(len(item) for item in fragmented_tokens) / max(
            len(native_text), 1
        )
        should_ocr = (
            force_ocr
            or fragmented_ratio > 0.08
            or (
                settings.ocr_enabled
                and len(native_text.strip()) < max(50, len(pdf) * 20)
            )
        )
        if not should_ocr:
            return OCRResult(
                text=native_text,
                page_count=len(pdf),
                used_ocr=False,
                confidence=None,
                lines=[
                    OCRLine(
                        page_number=page_number,
                        line_number=line_number,
                        text=line,
                        confidence=None,
                        bbox=None,
                    )
                    for page_number, page_text in enumerate(native_pages, start=1)
                    for line_number, line in enumerate(page_text.splitlines(), start=1)
                    if line.strip()
                ],
            )
        scale = settings.ocr_dpi / 72
        pages: list[str] = []
        confidences: list[float] = []
        lines: list[OCRLine] = []
        for page in pdf:
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(scale, scale),
                alpha=False,
            )
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            text, confidence, page_lines = _ocr_image(image, len(pages) + 1)
            pages.append(text)
            lines.extend(page_lines)
            if confidence is not None:
                confidences.append(confidence)
        return OCRResult(
            text="\n\n".join(pages),
            page_count=len(pdf),
            used_ocr=True,
            confidence=sum(confidences) / len(confidences) if confidences else None,
            lines=lines,
        )

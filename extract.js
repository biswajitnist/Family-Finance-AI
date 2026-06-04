const fs = require('fs');
const path = require('path');
const pdfParse = require('pdf-parse');
const Tesseract = require('tesseract.js');
const XLSX = require('xlsx');

async function extractText(filePath, originalName) {
  const ext = path.extname(originalName || filePath).toLowerCase();
  if (ext === '.pdf') {
    const data = await pdfParse(fs.readFileSync(filePath));
    return { text: data.text, type: 'PDF' };
  }
  if (['.png','.jpg','.jpeg','.webp','.bmp','.tiff'].includes(ext)) {
    const result = await Tesseract.recognize(filePath, 'eng+deu');
    return { text: result.data.text, type: 'OCR Image' };
  }
  if (['.xlsx','.xls'].includes(ext)) {
    const wb = XLSX.readFile(filePath);
    let text = '';
    wb.SheetNames.forEach(name => {
      text += `\nSheet: ${name}\n`;
      const rows = XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1, raw: false });
      text += rows.map(r => r.join(' | ')).join('\n');
    });
    return { text, type: 'Excel' };
  }
  if (['.csv','.txt'].includes(ext)) {
    return { text: fs.readFileSync(filePath, 'utf8'), type: ext === '.csv' ? 'CSV' : 'Text' };
  }
  throw new Error(`Unsupported file type: ${ext}`);
}

module.exports = { extractText };

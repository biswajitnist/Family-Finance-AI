# Ledger Local Development Statistics

Measured on 12 June 2026.

## Executive Summary

| Metric | Current count | Basis |
|---|---:|---|
| Functional product areas | 22 | User-facing modules and major workflows |
| Backend API operations | 111 | FastAPI route decorators |
| Backend services | 20 | Service modules |
| Database models | 28 | SQLAlchemy model classes |
| API/schema models | 68 | Request and response schema classes |
| Frontend components | 23 | React component files |
| Automated test cases | 40 | Pytest test functions |
| Test script files | 7 | Backend `test_*.py` files |
| Python source files | 59 | Application and test files |
| TypeScript/React source files | 30 | Frontend `.ts` and `.tsx` files |
| Documentation guides | 5 | Markdown files in `docs`, including this report |
| Development/runtime scripts | 4 | Shell scripts in `scripts` |
| Total application and test LOC | 24,845 | Physical source lines |
| Documentation LOC | 256 before this report | Physical Markdown lines |
| Production deployment definitions | 0 | No Docker, CI/CD, cloud, or hosting manifest found |
| Local runtime services | 2 | FastAPI backend and Vite frontend |

## Lines of Code

| Area | Lines |
|---|---:|
| Backend application | 9,506 |
| Backend tests | 1,777 |
| Frontend TypeScript and React | 8,206 |
| Frontend CSS | 5,356 |
| **Total** | **24,845** |

The counts include blank lines and comments because they are physical lines of
source. Generated frontend build output, SQLite databases, uploaded documents,
ChromaDB files, dependencies, and cache files are excluded.

## Functional Coverage

The application currently contains 22 major functional areas:

1. Dashboard and financial overview
2. Accounts
3. Transactions
4. Categories and category icon configuration
5. Classification rules
6. Monthly budgets
7. Recurring transaction detection and budget proposals
8. Document upload and local storage
9. PDF, image, CSV, Excel, and text extraction
10. Tesseract OCR
11. Local Ollama extraction and classification
12. Verifiable statement audit and reconciliation
13. Duplicate and overlapping screenshot detection
14. Investments and portfolio grouping
15. Watchlist and market data
16. Loans and debt analysis
17. Property and real-estate tracking
18. Retirement and pension tracking
19. Insurance
20. Reports and cash-flow analysis
21. Finance AI and in-app Help Agent
22. Settings, provider configuration, backup, and security controls

The 111 API operations are distributed across accounts, categories,
transactions, documents, statement sets, budgets, reports, investments,
watchlists, loans, properties, retirement, insurance, market data, analytics,
dashboard, AI, profile, recurrence, OCR, health, and backup APIs.

## Quality Statistics

- 40 automated backend test cases currently pass.
- Ruff static checks pass.
- Python compilation passes.
- TypeScript compilation and the Vite production build pass.
- Statement-audit tests cover multi-document batches, reconciliation counts,
  overlap removal, and final confirmation.
- Browser acceptance checks have been performed against the local application.

Automated frontend component tests and a formal end-to-end browser test suite
are not yet present. Browser verification is currently manual.

## Iterations and Human Intervention

The repository has no usable Git commit history, issue tracker export, release
tags, or deployment log. Therefore, exact counts for development iterations,
hours, deployments, and individual code changes cannot be reconstructed
reliably.

From the visible development conversation, there were at least **52 explicit
human requirement, correction, verification, or design-feedback interventions**
before this report. These included:

- Feature requirements and prioritization
- Screenshot-based UI reviews
- Manual statement-extraction verification
- Identification of missing and duplicate transactions
- Financial-domain clarification
- Approval of audit and reconciliation behavior
- Repeated acceptance testing and correction requests

Human involvement has therefore been **high in product direction and
acceptance**, while implementation, code generation, refactoring, automated
testing, and most technical diagnosis were AI-assisted.

An exact human-hours percentage would be misleading without time tracking.
A reasonable qualitative allocation is:

| Activity | Primary involvement |
|---|---|
| Product requirements | Human-led |
| Financial workflow decisions | Human-led with AI support |
| UI acceptance and screenshots | Human-led |
| Architecture and implementation | AI-assisted |
| Automated testing and static checks | AI-executed, human-requested |
| Real-data validation | Human-led with AI investigation |
| Final acceptance | Human-controlled |

## Deployment Status

Ledger Local currently uses a local development deployment:

- FastAPI/Uvicorn backend on the local machine
- React/Vite frontend on the local machine
- SQLite and ChromaDB local storage
- Tesseract and Ollama local processing

No evidence of a production deployment, cloud deployment, CI/CD pipeline,
Docker image, release tag, or formal environment promotion was found.
Repeated local server restarts occurred during development, but they are not
counted as deployments because no durable deployment log exists.

## Improving Future Measurement

To make future statistics exact, add:

- Git commits and release tags
- A changelog with feature identifiers
- CI test and build history
- Deployment environment records
- Issue and acceptance-test tracking
- Optional development time tracking
- Test coverage reporting
- A version/build table stored in SQLite

This would allow exact reporting of lead time, iteration count, deployment
frequency, defect rate, test coverage, and human review effort.

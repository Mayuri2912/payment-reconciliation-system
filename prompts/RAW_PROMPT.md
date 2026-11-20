# MASTER PROMPT: ONELAB AI NATIVE ENGINEER ASSESSMENT – COMPLETE WORKING SOLUTION

## ROLE AND EXPECTATIONS

Act as a Senior Software Engineer, FinTech Solutions Architect, Full-Stack Developer, Data Engineer, Financial Reconciliation Specialist, QA Engineer and AI-assisted coding partner.

You are assisting me with the Onelab AI Native Engineer Intern assessment (November 2026).

This is explicitly an AI-assisted engineering assessment. You are expected to actively participate in analysing, designing, developing, debugging, testing and documenting the solution.

Your responsibility is to help me produce a complete, functional, technically sound and demonstrable engineering solution.

Do not restrict yourself to theoretical explanations, pseudocode or partial code snippets. Take an active role in building the actual working application.

Prioritise correctness, completeness, practical implementation and transparent documentation.

---

# PART 1: OFFICIAL ASSESSMENT PROBLEM

## The Problem

A payments company's books don't balance at month end.

They know every transaction their platform processed. They know what the bank says actually arrived.

The two should match.

They don't.

Find out why. Show them where the gaps are.

## Test Data

No files are provided. Generate your own. This is part of the assessment.

A payments platform records a transaction instantly when a customer pays. The bank batches and settles funds 1–2 days later.

At month end every transaction should have a matching settlement.

You MUST deliberately introduce and detect these four gap types:

1. A transaction that settled the following month.
2. A rounding difference that only shows when summed.
3. A duplicate entry in one dataset.
4. A refund with no matching original transaction.

State your assumptions. There are no wrong ones as long as you name them.

## Official Submission Requirements

1. Brainstorming thread – Full LLM conversation. Do not clean it up.
2. Distilled prompt and Raw Prompt – The single prompt fed into Claude Code, Cursor or another AI coding tool.
3. Claude Code thread – Full execution thread, including wrong turns.
4. Test cases – What was written to verify the solution works.
5. Working output:
   - Deployed link.
   - Code ZIP.
   - Demo video.
   - Three sentences explaining what the solution would get wrong in production.

The assessment allows any AI tools and has a duration of two hours.

---

# PART 2: PRIOR BRAINSTORMING CONTEXT

IMPORTANT: I HAVE ALREADY CONDUCTED A SEPARATE BRAINSTORMING DISCUSSION WITH CLAUDE BEFORE STARTING THIS IMPLEMENTATION.

The brainstorming discussion covered the business problem, reconciliation methodology, four mandatory discrepancy types, synthetic data generation, technical approaches, architecture, assumptions and implementation strategy.

This is not a fresh brainstorming exercise.

The implementation must continue from the decisions and conclusions reached during that brainstorming discussion.

I will provide the brainstorming transcript, exported document or relevant discussion when available.

### Instructions for using the brainstorming context

1. Read the provided brainstorming material carefully before making major technical decisions.
2. Extract the final agreed assumptions and technical decisions.
3. Use them as the foundation for implementation.
4. Do not unnecessarily repeat brainstorming that has already been completed.
5. Identify any technical weaknesses in the earlier discussion and recommend corrections.
6. Explain important changes rather than silently changing previously agreed decisions.
7. Maintain consistency between the brainstorming, implementation prompt, source code, tests and final submission.

If the brainstorming transcript is not yet available, proceed using the official assignment requirements and clearly identified assumptions. Do not pretend to have read a conversation you cannot access.

---

# PART 3: PROJECT OBJECTIVE

Build a complete Payment Reconciliation and Discrepancy Detection System.

The application must compare:

A. Payment platform transaction records.

B. Bank settlement records.

It must identify where the records do not match, explain the reason for each discrepancy, calculate financial differences and provide a clear reconciliation report.

The application should demonstrate the complete reconciliation process using realistic synthetic data.

The objective is not simply to display four hardcoded discrepancy examples.

The objective is to build reusable detection logic that identifies discrepancies from the actual contents of the datasets.

---

# PART 4: TECHNICAL STACK AND ARCHITECTURE

Use the following preferred technology stack:

### Backend
- Python.
- FastAPI.
- Pandas.
- SQLite where persistence is useful.

### Frontend
- React.
- Vite.
- Recharts.
- Modern CSS or Tailwind CSS.

### Financial calculations
- Python Decimal.
- Explicit monetary rounding rules.
- Configurable reconciliation tolerance.

### Development tools
- Git.
- VS Code.
- Terminal.
- Claude Code.

Before selecting the final architecture, consider the brainstorming decisions.

Prioritise a simple, reliable architecture that can be implemented within the two-hour assessment.

Do not introduce unnecessary technologies, microservices or complex infrastructure.

If a different stack is substantially more practical, explain the reason and use it only when it improves reliability or implementation speed.

---

# PART 5: SYNTHETIC DATA GENERATION

No actual transaction or settlement datasets have been supplied.

Generate your own reproducible datasets.

Create at least two datasets.

## A. PLATFORM TRANSACTIONS

Include:

- Transaction ID.
- Transaction timestamp.
- Transaction date.
- Transaction type: PAYMENT or REFUND.
- Original transaction reference for refunds.
- Gross transaction amount.
- Currency.
- Transaction status.

## B. BANK SETTLEMENT RECORDS

Include:

- Settlement ID.
- Transaction ID.
- Settlement date.
- Settlement amount.
- Settlement batch ID.
- Currency.
- Settlement status.

Use realistic November and December dates to demonstrate month-end reconciliation.

Include normal transactions as well as the four deliberately planted discrepancies.

Use a fixed random seed so that the datasets can be regenerated consistently.

Save the datasets as downloadable CSV files.

Create sufficient normal records so the application demonstrates actual reconciliation rather than simply identifying four predetermined examples.

Document all data-generation assumptions.

---

# PART 6: MANDATORY DISCREPANCY DETECTION

This is the most important part of the assessment.

All four discrepancies must be implemented, tested and clearly visible in the final application.

## 1. NEXT-MONTH SETTLEMENT

Create a transaction recorded in November that is settled in December.

The system must:

- Identify the transaction ID.
- Show the platform transaction date.
- Show the actual bank settlement date.
- Recognise the month boundary.
- Classify it as a next-month settlement.
- Explain why it should not automatically be treated as a permanently missing transaction.

Demonstrate how the settlement timing affects month-end reconciliation.

## 2. AGGREGATE ROUNDING DIFFERENCE

Introduce small decimal precision differences that may appear insignificant individually but become visible when aggregated.

The system must:

- Calculate individual differences.
- Calculate aggregate differences.
- Use Decimal-based monetary arithmetic.
- Apply an explicitly documented rounding methodology.
- Show how the cumulative difference arises.
- Explain the difference between transaction-level and aggregate-level rounding.

Do not artificially create a large discrepancy and call it rounding.

## 3. DUPLICATE ENTRY

Insert a duplicate record into exactly one of the datasets.

The system must:

- Detect duplicate transaction identifiers.
- Identify the dataset containing the duplicate.
- Display the duplicate record.
- Explain why it is considered a duplicate.
- Prevent the duplicate from being counted twice in financial totals.
- Preserve the original records for auditing.

## 4. ORPHAN REFUND

Create a refund with no matching original payment.

The system must:

- Identify the refund.
- Display the refund ID.
- Check the original transaction reference.
- Identify the missing original payment.
- Classify it as an orphan refund.
- Explain why the record cannot be matched.

IMPORTANT:

Do not simply hardcode the discrepancy results.

Implement reusable detection algorithms that examine the actual datasets.

Do not classify every unmatched transaction as missing.

Account for legitimate settlement delays, refunds, duplicates and rounding differences.

---

# PART 7: RECONCILIATION ENGINE

Build a reusable reconciliation engine separate from the frontend.

It should support:

1. Transaction matching.
2. Amount comparison.
3. Duplicate identification.
4. Next-month settlement identification.
5. Aggregate rounding analysis.
6. Orphan refund detection.
7. Missing settlement detection.
8. Unexpected bank transaction identification.
9. Aggregate financial reconciliation.
10. Detailed discrepancy reporting.

Calculate:

- Total platform payment amount.
- Total bank settlement amount.
- Total matched amount.
- Total unmatched amount.
- Total duplicate amount excluded.
- Total discrepancy amount.
- Aggregate reconciliation difference.

Clearly distinguish gross payments, refunds, settlement amounts and any fees that are actually represented in the data.

Do not silently assume bank settlement equals gross payment when fees or adjustments are present.

For the synthetic dataset, explicitly document whether settlement amounts represent gross or net amounts.

Use consistent sign conventions for payments, refunds and differences.

Keep the reconciliation logic modular, readable and testable.

---

# PART 8: DASHBOARD AND USER INTERFACE

Develop a professional, modern FinTech dashboard.

The interface should look like a real payment operations and reconciliation product.

Prioritise clarity, usability and actual working functionality over decorative design.

## A. OVERVIEW DASHBOARD

Display:

- Total platform transactions.
- Total bank settlement records.
- Total platform payment amount.
- Total bank settlement amount.
- Matched transactions.
- Unmatched transactions.
- Total discrepancy count.
- Total discrepancy amount.
- Overall reconciliation status.

Include useful charts and visual summaries.

## B. TRANSACTION MANAGEMENT

Provide separate views for:

- Platform transactions.
- Bank settlement records.

Display:

- Transaction ID.
- Transaction type.
- Transaction amount.
- Transaction date.
- Settlement date.
- Status.
- Matching result.

Include search, filters and useful sorting.

## C. DISCREPANCY ANALYSIS

Create a dedicated section with four separate categories:

1. Next-month settlements.
2. Rounding differences.
3. Duplicate entries.
4. Orphan refunds.

Each discrepancy should display:

- Discrepancy type.
- Relevant transaction ID.
- Settlement ID, where applicable.
- Dataset containing the issue.
- Expected amount.
- Actual amount.
- Financial difference.
- Relevant dates.
- Explanation.
- Suggested corrective action.

## D. RECONCILIATION REPORT

Provide:

- Overall reconciliation summary.
- Matched transactions.
- Unmatched transactions.
- Discrepancy breakdown.
- Aggregate financial differences.
- Reconciliation status.
- Important observations.

## E. DATA MANAGEMENT

Allow the user to:

- Generate synthetic datasets.
- View the generated datasets.
- Download platform transaction CSV.
- Download bank settlement CSV.
- Upload custom CSV datasets if feasible.
- Run reconciliation again.

## F. EXPORT

Provide a working option to download the reconciliation report as CSV.

If PDF export is practical within the available time, include it as an additional feature.

---

# PART 9: TESTING AND VALIDATION

Create automated tests using an appropriate Python testing framework, preferably pytest.

At minimum, test:

1. Correct transaction matching.
2. Next-month settlement detection.
3. Aggregate rounding difference detection.
4. Duplicate detection in platform data.
5. Duplicate detection in bank data.
6. Orphan refund detection.
7. Missing settlement identification.
8. Unexpected bank transaction detection.
9. Empty datasets.
10. Invalid records.
11. Duplicate exclusion from aggregate calculations.
12. Correct financial calculations.
13. Correct refund treatment.
14. Consistent reconciliation results when datasets are regenerated.

For each test, document:

- Test case ID.
- Test objective.
- Input data or scenario.
- Expected result.
- Actual result.
- Pass/fail status.

Execute the tests.

Fix any discovered implementation errors.

Never claim that a test has passed unless it has actually been executed.

Ensure that the four mandatory discrepancies are demonstrably detected in the generated dataset.

---

# PART 10: PROJECT DOCUMENTATION

Prepare a complete README.md.

Include:

1. Project title.
2. Problem statement.
3. Business objective.
4. Key features.
5. Technology stack.
6. Architecture overview.
7. Project structure.
8. Synthetic data description.
9. Data dictionary.
10. Assumptions.
11. Reconciliation methodology.
12. Discrepancy detection logic.
13. Financial calculation methodology.
14. Installation instructions.
15. Execution commands.
16. Test execution instructions.
17. Sample results.
18. Known limitations.
19. Future improvements.

Include a simple architecture diagram or data-flow diagram if practical.

Documentation must describe the actual implementation, not features that were merely planned.

---

# PART 11: RAW PROMPT AND DISTILLED PROMPT

The assessment explicitly requires both.

## RAW PROMPT

Preserve the exact complete original prompt submitted to Claude Code for implementation.

Do not silently rewrite it afterwards.

## DISTILLED PROMPT

Prepare a concise and refined version of the implementation prompt that captures:

- The actual business problem.
- Required datasets.
- Four mandatory discrepancies.
- Reconciliation logic.
- Technical stack.
- Functional requirements.
- Testing requirements.
- Final deliverables.

Keep the distilled prompt separate from the raw prompt.

Ensure both documents reflect the actual project.

---

# PART 12: CLAUDE BRAINSTORMING AND EXECUTION THREADS

Both conversations are important assessment evidence.

## A. PRIOR CLAUDE BRAINSTORMING CONVERSATION

I have already conducted a separate Claude brainstorming discussion.

Maintain consistency with that discussion.

If I provide its transcript or exported document, review it and use the agreed decisions.

At the end, remind me to generate and verify a shareable link to the actual brainstorming conversation through Claude's interface.

## B. CLAUDE CODE EXECUTION CONVERSATION

This implementation conversation is also a required deliverable.

Preserve:

- Initial implementation prompt.
- Architecture decisions.
- Technical discussions.
- Code generation.
- Incorrect approaches.
- Errors.
- Debugging attempts.
- Corrections.
- Actual execution results.
- Testing.
- Final implementation decisions.

Do not artificially manufacture mistakes or remove genuine unsuccessful attempts.

Keep the implementation in one continuous Claude Code conversation wherever possible.

Avoid unnecessary new conversations.

If a continuation is unavoidable because of context or usage limits, prepare a detailed progress summary and preserve the original conversation.

At completion, remind me to create and verify a shareable Claude Code conversation link, if the interface supports it.

Do not claim that a share link exists unless it has actually been generated.

---

# PART 13: WORKING OUTPUT – FINAL DELIVERABLES

The assessment specifically requires the following.

## A. DEPLOYED APPLICATION LINK

Prepare the application for deployment.

If supported deployment tools and credentials are available:

- Deploy the frontend and backend.
- Configure the required environment variables.
- Verify that the deployed application actually loads.
- Test the important functionality.
- Provide the real working URL.

If deployment cannot be completed because of unavailable credentials, account restrictions or time limitations:

- Explain the exact limitation.
- Provide deployment instructions.
- Do not invent a deployment URL.
- Ensure the local application works.

## B. SOURCE CODE ZIP

Generate a ZIP archive containing:

- Complete frontend source code.
- Complete backend source code.
- Reconciliation engine.
- Synthetic data generator.
- Automated tests.
- Sample datasets.
- README.md.
- Requirements file.
- package.json and necessary configuration.
- Relevant documentation.

Exclude:

- node_modules.
- Python virtual environments.
- Cache folders.
- Unnecessary temporary files.
- API keys.
- Passwords.
- Other secrets.

Verify that the ZIP exists and contains the expected files.

## C. DEMO VIDEO

Prepare a concise demonstration of the actual application.

The demo should show:

1. Application launch.
2. Dashboard overview.
3. Synthetic dataset generation.
4. Platform transaction records.
5. Bank settlement records.
6. Reconciliation execution.
7. Next-month settlement detection.
8. Aggregate rounding difference.
9. Duplicate entry detection.
10. Orphan refund detection.
11. Reconciliation report.
12. CSV export.

If direct screen recording is unavailable, prepare a practical recording script with the exact sequence of actions.

Do not claim that a demo video exists unless it has actually been recorded.

## D. THREE PRODUCTION LIMITATION SENTENCES

Prepare exactly three meaningful sentences describing what this implementation would get wrong or fail to handle reliably in a real financial environment.

Base these sentences on the actual system limitations.

Do not use generic limitations that do not apply to the implementation.

---

# PART 14: DEVELOPMENT EXECUTION STRATEGY

The assessment duration is two hours.

Time management is extremely important.

Follow this priority order.

### PRIORITY 1 – CORE ENGINE

- Create synthetic datasets.
- Implement all four mandatory discrepancies.
- Build reusable reconciliation logic.
- Ensure financial calculations are correct.

### PRIORITY 2 – FUNCTIONAL APPLICATION

- Implement backend.
- Implement frontend.
- Connect APIs.
- Display actual reconciliation results.
- Enable CSV exports.

### PRIORITY 3 – VALIDATION

- Create automated tests.
- Execute tests.
- Fix errors.
- Verify all four discrepancies.

### PRIORITY 4 – SUBMISSION PREPARATION

- README.
- Assumptions.
- Distilled prompt.
- Source ZIP.
- Deployment.
- Demo video.

Prioritise a working, tested application over unnecessary visual complexity.

Do not spend excessive time adding features that are not required by the assessment.

If time becomes limited, complete the core requirements first and clearly document anything that remains unfinished.

---

# PART 15: CODING AND EXECUTION RULES

Follow these instructions throughout implementation:

1. Inspect the working directory before creating or modifying files.
2. Do not overwrite existing files without checking them.
3. Use a clean and modular project structure.
4. Write complete executable code.
5. Avoid unnecessary dependencies.
6. Include appropriate input validation and error handling.
7. Use meaningful variable and function names.
8. Do not hardcode discrepancy results.
9. Do not fabricate data-processing outputs.
10. Do not fabricate test results.
11. Execute the actual commands.
12. Read and diagnose errors before changing code.
13. Fix errors and rerun the relevant tests.
14. Keep track of created files and completed tasks.
15. Ensure the frontend displays actual backend results.

Do not repeatedly ask for confirmation before routine implementation steps.

When requirements are sufficiently clear, proceed using documented assumptions.

If an essential decision is missing, ask only the most important clarification.

---

# PART 16: RESPONSE CONTINUITY

Do not unnecessarily stop in the middle of an implementation.

Complete each development phase systematically.

If a response becomes too long:

- Divide it into numbered sections.
- Clearly identify what has been completed.
- Identify what remains.
- Continue from the exact stopping point when I ask you to continue.

If the context becomes full, prepare a detailed continuation summary containing:

- Assessment requirements.
- Final architecture.
- Agreed assumptions.
- Project folder location.
- Current project structure.
- Files created.
- Commands executed.
- Actual test results.
- Errors encountered.
- Fixes applied.
- Remaining work.
- Exact next action.

Never pretend that incomplete work has been completed.

---

# PART 17: FINAL ACCEPTANCE CHECKLIST

Before declaring the project complete, verify each requirement.

1. Application runs locally.
2. Synthetic platform transactions are generated.
3. Synthetic bank settlements are generated.
4. Next-month settlement is detected.
5. Aggregate rounding difference is detected.
6. Duplicate entry is detected.
7. Orphan refund is detected.
8. Financial calculations are accurate.
9. Duplicate entries do not distort totals.
10. Dashboard displays actual reconciliation results.
11. Discrepancy details are visible.
12. CSV report can be downloaded.
13. Automated tests have been executed.
14. README is available.
15. Assumptions are documented.
16. Raw prompt is preserved.
17. Distilled prompt is prepared.
18. Source code ZIP is created and verified.
19. Deployment status is honestly reported.
20. Demo video or recording guide is prepared.
21. Exactly three production limitation sentences are prepared.
22. Brainstorming conversation share link is ready to be generated through Claude's interface.
23. Claude Code execution conversation share link is ready to be generated through Claude's interface.

---

# FINAL INSTRUCTION

This is a serious engineering assessment.

Act as an active AI engineering collaborator rather than a passive tutor.

Use the brainstorming already completed as the foundation.

Build the actual working application.

Generate realistic synthetic datasets.

Implement reusable discrepancy detection algorithms.

Verify the results through executed tests.

Prepare all required working-output deliverables.

Preserve the genuine brainstorming and implementation history for assessment review.

Be proactive, technically accurate, transparent and efficient.

Do not stop at a dashboard mockup, architecture proposal or code snippets.

The final objective is a working, tested, demonstrable Payment Reconciliation and Discrepancy Detection System that satisfies the official Onelab assessment requirements.

START BY INSPECTING THE WORKING DIRECTORY AND REVIEWING THE AVAILABLE BRAINSTORMING CONTEXT. THEN PROCEED WITH IMPLEMENTATION SYSTEMATICALLY.
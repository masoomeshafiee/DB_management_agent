# Database Management Agent

An LLM-powered, agent-based database management system designed to help non-technical biologists interact safely and effectively with a laboratory SQLite database using natural language.

This project uses Google Agent Development Kit (ADK) to translate human-language requests into validated, auditable database operations, without requiring SQL knowledge, lowering the barrier to good data management practices in experimental biology labs.

Status: Active development

This repository contains Version 1, focused on correctness, safety, and observability.


#### **Problem Motivation**

Many biology labs rely on relational databases (often SQLite) to store experimental metadata, yet:
- Most users do not know SQL
- Direct database access increases the risk of accidental data loss
- Validation, auditing, and reproducibility are often missing or ad hoc

This project addresses these challenges by introducing an agent-based intermediary that:
- Accepts natural language requests
- Routes tasks to specialized agents
- Executes predefined, safe Python query builders
- Logs all actions for traceability and recovery

#### **Core Objective**
To build an LLM-powered database manager that enables non-technical users to:
- Search records
- Insert validated data
- Delete records with explicit confirmation
- Maintain traceable, auditable database interactions

All without writing SQL.


#### **High-Level Architecture**

The system follows a multi-agent design, orchestrated by a root agent:

**User (Natural Language)** --> **Root Agent (reasoning)** --> **Specialized Sub-Agents** --> **Python Query Builders** --> **SQLite Database**
                

 
##### **Important Note:**
1. The system does not allow free-form SQL generation.
Instead, agents select from explicit, tested Python query builders, ensuring safety and traceability. This:
- Prevents hallucinated or unsafe SQL
- Makes behavior deterministic
- Enables unit testing

2. **Python Database Layer Dependency**

The Python layer that directly interfaces with the database—and whose modules are exposed to the agent system as tools—is developed and maintained in a separate repository:
https://github.com/masoomeshafiee/data-management-system-SQLite

To use the agent-based database manager, the `lab-data-manager` package (the Python database layer) must be installed in your environment.

#### **Agent Design**

##### Root Agent:
- Interprets the user request
- Decides which sub-agent(s) to invoke
- Coordinates multi-step workflows

##### 
##### Filter Agent:
- Extracts structured filters from natural language
- Produces filter dictionaries used by query builders

##### Validation Agent:
- Validates records prior to insertion
- Ensures schema consistency
- Checks required fields, data types and format correctness

##### Search Agent:
- Executes safe, parameterized read-only queries
- Returns records matching user-defined criteria


##### Insert Agent:
- Inserts validated records
- Supports CSV-based ingestion


##### Insert Manager Agent (Sequential):
- Runs Validation → Insert
- Inserts validated records and reutrns skipped records (due to dupliacation, etc)

##### Delete Agent (Long-Running):
- Performs dry-run analysis
- Estimates deletion impact
- Reports the number of candidate records for deletion
- Waits for user approval


##### Delete Manager Agent (Sequential):
- Runs Filter → Delete
- Explicitly requests human approval before deletion

#### Features: 
**Natural Language Interface:**
Users express requests in plain English, for instance:
- “Show all experiments from yeast cells in January”
- “Insert this metadata CSV”
- “Delete all the invalid experiments from last week”

**Multi-Agent Task Decomposition:**
Requests are routed to specialized agents:
- Filtering
- Validation
- Search
- Insert
- Delete (with confirmation)

**Safe Database Operations:**
- No raw SQL exposed to users
- Parameterized Python query builders only
- Validation enforced before insertion
- Human approval required for deletions

**Memory & Session Management:**
- Uses InMemorySessionService (v1)
- Maintains conversational state during interactions
- Designed to be replaced with persistent memory in later versions

**Observability & Auditing:**
Every database interaction is logged via a post-query plugin:
- User request (natural language)
- Agents invoked
- Summary of actions performed
- Query outcomes

This enables:
- Debugging agent behavior
- Tracking unintended changes
- Supporting future rollback mechanisms


#### Input & Output Examples:

##### Example 1 — Search:

**User input**
```
Find all experiments with organism = yeast with laser time exposure = 30 ms. 
```
**Agent output**
Along the `csv file` containing the records found, it will return:
```
{
  "records_returned": 42,
  "filters_applied": {
    "organism": "yeast",
    "exposure_time": ">30"
  }
}
```
##### Example 2 — Insert (CSV)

**User input**
```
Insert the records from metadata_run_12.csv
```
**Agent behavior**
- Validate schema and field formats
- Reject invalid rows
- Insert only validated records

**Agent outputs:**
Along the `csv file` containing the `invalidated/skipped` records , it will return:
```
{
  "rows_validated": 120,
  "rows_inserted": 117,
  "rows_rejected": 3
}
```
##### Example 3 — Delete (Human-in-the-loop)
**User input**
```
Delete all invalid experiments from March.
```
**Dry run output**
```
{
  "candidate_records": 18,
  "action": "pending_user_approval"
}
```
Deletion proceeds only after confirmation.

### Project Structure:
```
db_management_agent/
├── agents/
├── utils/
├── memory/
├── observability/
├── config/
├── test/
├── main.py
├── workflow.py
└── README.md
```

#### Technologies Used:
- Python
- SQLite
- Google Agent Development Kit (ADK)
- LLM-based agent orchestration

#### Getting Started
**Prerequisites**
- Python ≥ 3.9
- SQLite
- Google ADK installed and configured

**Installation**
```
git clone https://github.com/masoomeshafiee/DB_management_agent.git
cd DB_management_agent
pip install -r requirements.txt
```
**Configuration**
Update database path and agent settings in:
``` 
config/config.yaml
```
**Usage**
```
python main.py
```
Example interaction:

**`User`**: Show all experiments from E.coli with protein DnaA.
**`Agent`**: Found 24 matching records.

#### Contributors
- **Masoumeh Shafiei**
- **Niusha Mirhakimi**


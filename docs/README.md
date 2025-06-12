# ResolveMeQ Documentation

## Overview

ResolveMeQ is a modular Django-based IT support and automation platform with Slack integration, ticketing, knowledge base, automation, and analytics.

---

## Apps & Features

### 1. **users**
- **Model:** `User`
  - `user_id` (Slack ID, primary key)
  - `name`, `email`, `role`, `department`
- **Purpose:** Represents end users and IT admins.

---

### 2. **tickets**
- **Model:** `Ticket`
  - `ticket_id`, `user`, `assigned_to`, `issue_type`, `status`, `description`, `screenshot`, `category`, `tags`, `created_at`, `updated_at`, `agent_response`, `agent_processed`
- **Model:** `TicketInteraction`
  - `id`, `ticket`, `user`, `interaction_type`, `content`, `created_at`
- **Features:**
  - Ticket creation via Slack modal (`/resolvemeq`)
  - Tracks all user and agent interactions (clarification, feedback, agent response, user message) for analytics and knowledge enrichment
  - Service categories (Wi-Fi, Laptop, VPN, etc.)
  - Tags for flexible triaging
  - Assignment to IT staff
  - CSV export, Slack notifications, escalation logic
  - Analytics endpoint (`/api/tickets/analytics/`)
  - **Automatic knowledge base enrichment:** Resolved tickets with agent responses are synced to the knowledge base as articles
- **Admin:** Assign, resolve, respond via Slack, export tickets

---

### 3. **solutions**
- **Model:** `Solution`
  - `solution_id`, `ticket`, `steps`, `worked`
- **Purpose:** Stores solutions for tickets.

---

### 4. **knowledge_base**
- **Model:** `KnowledgeBaseArticle`
  - `kb_id`, `title`, `content`, `tags`, `created_at`, `updated_at`, `views`, `helpful_votes`, `total_votes`
- **Features:**
  - Internal knowledge base for IT and users
  - **Auto-enrichment:** New articles are created/updated from resolved tickets and agent responses

---

### 5. **automation**
- **Model:** `AutomationTask`
  - `task_id`, `command`, `parameters`, `status`, `result`, `executed_at`
- **Purpose:** Tracks and logs automation tasks.

---

### 6. **integrations**
- **Model:** `SlackToken`
  - `access_token`, `team_id`, `bot_user_id`, `created_at`
- **Views:**
  - Slack OAuth (`/api/integrations/slack/oauth/redirect/`)
  - Slack Events (`/api/integrations/slack/events/`)
  - Slash Commands (`/api/integrations/slack/commands/`)
  - Interactive Actions (`/api/integrations/slack/actions/`)
  - Modal Submission (`/api/integrations/slack/modal/`)
- **Features:**
  - Slack bot for ticket creation, status, notifications, escalation
  - Request verification using Slack signing secret

---

## Key Features

- **Slack Integration:**  
  - Create tickets, check status, receive notifications, escalate urgent issues.
- **Admin Dashboard:**  
  - Assign, resolve, and respond to tickets. Export and analyze ticket data.
- **Analytics:**  
  - Tickets per week, average resolution time, open vs closed tickets.
- **Escalation:**  
  - Urgent tickets not updated in 2 hours trigger Slack alerts.
- **Service Categories & Tags:**  
  - For faster triaging and reporting.

---

## API Documentation

- Swagger UI: `/docs/`
- Redoc: `/redoc/`
- Example endpoint: `/api/tickets/analytics/`

---

## Onboarding & Setup

1. Clone the repo and install dependencies.
2. Set up your `.env` file with Slack credentials.
3. Run migrations: `python manage.py migrate`
4. Start the server: `python manage.py runserver`
5. Configure your Slack app and invite the bot to your workspace.

---

## Architecture

- Django backend with modular apps
- Slack bot integration for real-time IT support
- REST API for frontend or external integrations

---

## Enhanced Slack Interactivity (2025-06)

- Every agent response in Slack now includes the following interactive buttons:
  - **Ask Again:** Reprocesses the ticket with the agent and posts an update in the thread.
  - **Provide More Info:** Opens a modal for the user to clarify or add details to the ticket.
  - **Escalate:** Escalates the ticket to IT admins and logs the escalation as a TicketInteraction.
  - **Cancel:** Cancels the current update or action and logs the cancellation.
  - **Mark as Resolved:** Marks the ticket as resolved, triggers knowledge base/suggestion enrichment, and prompts for feedback.
- All button actions are logged as TicketInteraction for analytics and knowledge enrichment.
- Escalation can optionally notify IT admins or a dedicated escalation channel.

---

## How Knowledge Enrichment Works

- Every ticket and user/agent interaction (clarification, feedback, agent response, escalation, etc.) is logged as a `TicketInteraction`.
- When a ticket is resolved and has an agent response, it is automatically added to the knowledge base as a new article (or updates an existing one).
- Solutions are created from agent responses with resolution steps.
- This enables the AI agent and IT team to learn from real support conversations and resolutions, improving future answers and automation.

---

For more details, see each app's code and the API docs.

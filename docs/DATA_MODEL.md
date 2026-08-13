PermitSignal Data Model

1. Purpose

This document defines the canonical information model used by PermitSignal.

The model is designed to preserve the original government evidence while progressively enriching the record with:

historical friction

future events

identity

public contact information

opportunity scoring

Do not remove existing fields simply to simplify the schema.

2. Application Record

The application extractor should produce records containing fields such as:

item
applicant_name
applicant_email
applicant_phone

staff_contact_name
staff_email
staff_phone

application_type
application_number
project_address
neighborhood
status

source
source_url
description

3. Applicant Identity Fields

Identity enrichment may add:

normalized_applicant_name
applicant_email
applicant_phone

email_domain
website_domain

company_name
company_website
company_domain

The original applicant name must remain available.

Do not overwrite an authoritative government-record identity with a weak external match.

4. Contact Intelligence Fields

The contact enrichment layer may populate:

contact_name
contact_role
contact_email
contact_phone
linkedin_url

Source metadata:

email_source
phone_source
company_source
contact_source

Confidence metadata:

email_confidence
phone_confidence
contact_confidence

Enrichment state:

enrichment_status
enrichment_method
contact_is_public
contact_is_verified

5. Government Contact Fields

Government staff contacts are separate from applicant contacts.

Use:

staff_contact_name
staff_email
staff_phone

Never use:

staff_email

as:

applicant_email

unless the source explicitly identifies that person as the applicant.

6. Friction Fields

Historical friction information includes:

friction_score
friction_signals
friction_events

An event may contain:

event_type
event_date
severity
confidence
relevance
source_page
evidence

Example:

{
  "event_type": "denied",
  "event_date": "2025-12-02",
  "severity": "critical",
  "confidence": 0.75,
  "relevance": 0.4,
  "evidence": "..."
}

Evidence should remain traceable.

7. Project Event Fields

Future project intelligence includes:

next_project_date
next_project_event
next_project_time
has_future_opportunity
days_until_event
urgency

Examples:

next_project_date = "2026-08-12"
next_project_event = "public_hearing"
next_project_time = "6:00 PM"

8. Date Safety

A date being future relative to the reference date does not mean it is a project event.

The system must distinguish:

project event

from:

administrative deadline

Examples of dates that should not automatically become next_project_date:

public comment deadline
submission deadline
day-before-hearing deadline
response deadline
cutoff date

For the current Provo packet:

2026-08-11

is an administrative/reference date.

The actual next project event is:

2026-08-12
public_hearing
6:00 PM

9. Opportunity Fields

The canonical opportunity includes:

application_number
applicant_name
applicant_email
applicant_phone

application_type
project_address
neighborhood
status

friction_score
friction_signals
friction_events

next_project_date
next_project_event
next_project_time

days_until_event
urgency

priority
priority_score

is_actionable
has_future_opportunity

opportunity_reason

10. Example Canonical Opportunity

{
  "application_number": "PLRZ20260264",
  "applicant_name": "Jared Morgan",
  "applicant_email": null,
  "applicant_phone": null,

  "application_type": "Zone Map Amendment",
  "project_address": "113/191 N Geneva Road",
  "neighborhood": "Fort Utah",

  "friction_score": 100,
  "friction_signals": [
    "denied",
    "recommended_denial"
  ],

  "next_project_date": "2026-08-12",
  "next_project_event": "public_hearing",
  "next_project_time": "6:00 PM",

  "days_until_event": 11,
  "urgency": "SOON",

  "priority": "HIGH",
  "priority_score": 180,

  "is_actionable": true,
  "has_future_opportunity": true
}

11. Enriched Example

After contact enrichment, the same record may become:

{
  "application_number": "PLRZ20260264",

  "applicant_name": "Jared Morgan",
  "applicant_email": null,
  "applicant_phone": null,

  "company_name": "Example Development LLC",
  "company_website": "https://example.com",
  "company_domain": "example.com",

  "contact_name": "Jared Morgan",
  "contact_role": "Developer",
  "contact_email": "jared@example.com",
  "contact_phone": null,

  "email_source": "official_company_website",
  "email_confidence": 0.95,

  "contact_source": "official_company_website",
  "contact_confidence": 0.95,

  "enrichment_status": "enriched",
  "enrichment_method": "public_web",
  "contact_is_public": true,
  "contact_is_verified": true,

  "application_type": "Zone Map Amendment",
  "project_address": "113/191 N Geneva Road",

  "friction_score": 100,
  "friction_signals": [
    "denied",
    "recommended_denial"
  ],

  "next_project_date": "2026-08-12",
  "next_project_event": "public_hearing",
  "next_project_time": "6:00 PM",

  "priority": "HIGH",
  "priority_score": 180
}

The example contact data above is schema-only. It must not be inserted into production unless independently found in a source.

12. Email Rules

Valid public email:

john@example.com

Potential generic mailbox:

info@example.com
contact@example.com
office@example.com
sales@example.com
hello@example.com

Generic addresses can still be useful, but should be distinguished from named professional addresses.

Reject obvious placeholders such as:

test@example.com
example@example.com

Reject malformed addresses.

Do not fabricate addresses.

If no evidence exists:

applicant_email = null
contact_email = null

13. Phone Rules

Store:

contact_phone
phone_source
phone_confidence

Do not fabricate numbers.

Preserve the original source value where useful, while also allowing normalized storage.

14. Source Precedence

Highest priority:

government_record

then:

official_company_website
official_team_page
public_business_directory
other_reputable_public_source

A lower-confidence source must not overwrite a higher-confidence government record.

15. Null Semantics

Null is valid.

Examples:

applicant_email = null
contact_email = null
company_name = null

This means:

The system does not currently have reliable evidence for this field.

It does not mean:

The field should be guessed.

16. Output Containers

Production JSON contains:

{
  "applications": [],
  "opportunities": [],
  "lead_queue": []
}

applications represent extracted/processed source records.

opportunities represent canonical business opportunities.

lead_queue represents sorted production candidates.

17. Data Integrity Principle

Every important enriched field should answer:

What is the value?
Where did it come from?
How confident are we?

Therefore contact intelligence should carry:

value
source
confidence

whenever possible.
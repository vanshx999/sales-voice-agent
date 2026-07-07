from .lead_manager import Lead, LeadManager


class CRMUpdater:
    def __init__(self, lead_manager: LeadManager):
        self.lead_manager = lead_manager

    def update_after_call(self, lead: Lead, call_result: dict):
        status_map = {
            "meeting_booked": "Meeting Booked",
            "interested": "Interested",
            "not_interested": "Not Interested",
            "no_answer": "No Answer",
            "timeout": "No Answer",
            "voicemail": "Left Voicemail",
        }

        qualification_map = {
            "yes": "Qualified",
            "maybe": "Maybe",
            "no": "Not Qualified",
        }

        lead.status = status_map.get(call_result.get("outcome", ""), "Completed")
        lead.qualification = qualification_map.get(
            call_result.get("qualification", ""), call_result.get("qualification", "")
        )
        lead.summary = call_result.get("summary", "")
        lead.requirements = call_result.get("requirements", "")
        lead.objections = call_result.get("objections", "")

        if call_result.get("follow_up"):
            lead.follow_up = call_result["follow_up"]

        if call_result.get("meeting_date"):
            lead.meeting_date = call_result["meeting_date"]

        if call_result.get("outcome") == "no_answer":
            lead.notes = f"No answer on {lead.last_contacted or 'last attempt'}"

        self.lead_manager.update_lead(lead)
        print(f"[CRMUpdater] Updated CRM for lead {lead.id}: {lead.status}")

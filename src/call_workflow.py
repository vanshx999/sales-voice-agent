import time
from datetime import datetime, timedelta
from typing import Optional

from .lead_manager import LeadManager, Lead
from .conversation_engine import ConversationEngine
from .voice_agent import VoiceAgent
from .crm_updater import CRMUpdater
from .utils import load_settings


class CallWorkflow:
    def __init__(
        self,
        lead_manager: Optional[LeadManager] = None,
        conversation_engine: Optional[ConversationEngine] = None,
        voice_agent: Optional[VoiceAgent] = None,
        crm_updater: Optional[CRMUpdater] = None,
    ):
        self.settings = load_settings()
        self.lead_manager = lead_manager or LeadManager()
        self.conversation_engine = conversation_engine or ConversationEngine()
        self.voice_agent = voice_agent or VoiceAgent(conversation_engine=self.conversation_engine)
        self.crm_updater = crm_updater or CRMUpdater(self.lead_manager)
        self.results: list[dict] = []

    def run_all(self, max_calls: int = 0) -> list[dict]:
        print("\n" + "=" * 60)
        print("SALES VOICE AGENT - CALL WORKFLOW")
        print("=" * 60)

        pending = self.lead_manager.get_pending_leads()
        if max_calls > 0:
            pending = pending[:max_calls]

        if not pending:
            print("[Workflow] No pending leads to call.")
            return []

        print(f"[Workflow] Processing {len(pending)} leads\n")

        for i, lead in enumerate(pending, 1):
            print(f"\n{'='*60}")
            print(f"[Workflow] Lead {i}/{len(pending)}: {lead.name} @ {lead.company}")
            print(f"{'='*60}")

            result = self.process_lead(lead)
            self.results.append(result)

            if i < len(pending):
                delay = 5
                print(f"\n[Workflow] Waiting {delay}s before next call...")
                time.sleep(delay)

        self._print_summary()
        return self.results

    def process_lead(self, lead: Lead) -> dict:
        try:
            result = self.voice_agent.make_call(lead.phone, lead)
            self.crm_updater.update_after_call(lead, result)

            if result.get("outcome") == "no_answer":
                retries = self.settings["call"]["max_retries"]
                delay_days = self.settings["call"]["retry_delay_days"]
                lead.notes = f"Retry scheduled in {delay_days} day(s). Attempts remaining: {retries - 1}"

            return result

        except Exception as e:
            print(f"[Workflow] Error processing lead {lead.id}: {e}")
            return {
                "lead_id": lead.id,
                "outcome": "error",
                "error": str(e),
            }

    def _print_summary(self):
        print("\n" + "=" * 60)
        print("CALL WORKFLOW SUMMARY")
        print("=" * 60)

        outcomes = {}
        for r in self.results:
            o = r.get("outcome", "unknown")
            outcomes[o] = outcomes.get(o, 0) + 1

        print(f"\nTotal leads processed: {len(self.results)}")
        print(f"Outcomes: {outcomes}")
        print()

        for r in self.results:
            print(f"  Lead {r.get('lead_id')}: {r.get('outcome', 'N/A')}")
            if r.get("summary"):
                print(f"    Summary: {r['summary'][:100]}...")
            print()

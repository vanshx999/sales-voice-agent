"""
Sales Voice Agent - Main Entry Point

Usage:
    python -m src.main                    # Interactive mode (single call)
    python -m src.main --all              # Process all pending leads
    python -m src.main --max 3            # Process 3 pending leads
    python -m src.main --demo             # Run demo mode (simulated conversation)
"""

import sys
import json
import argparse

from .utils import load_env, load_settings
from .lead_manager import LeadManager
from .conversation_engine import ConversationEngine
from .voice_agent import VoiceAgent
from .crm_updater import CRMUpdater
from .call_workflow import CallWorkflow


def run_interactive(use_mic=False):
    lead_manager = LeadManager()
    pending = lead_manager.get_pending_leads()
    if not pending:
        print("No pending leads.")
        return

    lead = pending[0]
    print(f"\nCalling: {lead.name} @ {lead.company} ({lead.phone})\n")

    engine = ConversationEngine()
    agent = VoiceAgent(conversation_engine=engine, use_mic=use_mic)
    updater = CRMUpdater(lead_manager)
    result = agent.make_call(lead.phone, lead)
    updater.update_after_call(lead, result)

    print("\nCall complete!")
    print(f"Outcome: {result.get('outcome')}")
    print(f"Summary: {result.get('summary', 'N/A')}")


def run_batch(max_calls: int = 0):
    workflow = CallWorkflow()
    workflow.run_all(max_calls=max_calls)


def run_demo(use_mic=False):
    print("\n" + "=" * 60)
    print("SALES VOICE AGENT - DEMO MODE")
    print("=" * 60)
    if use_mic:
        print("\nSpeak into your microphone. Say 'goodbye' to end.\n")
    else:
        print("\nType your responses as the prospect.\n")

    lead_manager = LeadManager()
    pending = lead_manager.get_pending_leads()
    if not pending:
        print("No pending leads for demo.")
        return

    lead = pending[0]
    engine = ConversationEngine()
    agent = VoiceAgent(conversation_engine=engine, use_mic=use_mic)

    print(f"Calling: {lead.name} @ {lead.company}")
    result = agent.make_call(lead.phone, lead)

    updater = CRMUpdater(lead_manager)
    updater.update_after_call(lead, result)

    print("\n" + "=" * 60)
    print("DEMO COMPLETE")
    print("=" * 60)
    print(json.dumps(result, indent=2))
    print()


def main():
    parser = argparse.ArgumentParser(description="Sales Voice Agent")
    parser.add_argument("--all", action="store_true", help="Process all pending leads")
    parser.add_argument("--max", type=int, default=0, help="Max leads to process")
    parser.add_argument("--demo", action="store_true", help="Run demo mode (simulated conversation)")
    parser.add_argument("--custom", nargs="?", const=True, default=False,
                        help="Demo with custom lead. Usage: --custom 'Name,Phone,Company'")
    parser.add_argument("--dry-run", action="store_true", help="Process leads without making calls")
    parser.add_argument("--interactive", action="store_true", help="Run interactive (default)")
    parser.add_argument("--mic", action="store_true", help="Use microphone for input instead of typing")

    args = parser.parse_args()

    load_env()

    if args.custom:
        run_custom(use_mic=args.mic, lead_info=args.custom if isinstance(args.custom, str) else None)
    elif args.demo:
        run_demo(use_mic=args.mic)
    elif args.dry_run:
        run_dry_run()
    elif args.all or args.max > 0:
        run_batch(max_calls=args.max)
    else:
        run_interactive(use_mic=args.mic)


def run_custom(use_mic=False, lead_info=None):
    print("\n" + "=" * 60)
    print("CUSTOM LEAD DEMO")
    print("=" * 60)
    if lead_info:
        parts = [p.strip() for p in lead_info.split(",")]
        name = parts[0] if len(parts) > 0 else "Test User"
        phone = parts[1] if len(parts) > 1 else "+15550000000"
        company = parts[2] if len(parts) > 2 else name
    else:
        name = input("Lead name: ").strip() or "Test User"
        phone = input("Phone (optional): ").strip() or "+15550000000"
        company = input("Company: ").strip() or "Test Company"
    print()

    from .lead_manager import Lead
    lead = Lead({"Lead ID": 999, "Name": name, "Phone Number": phone,
                 "Email": "", "Company": company, "Call Status": "Pending",
                 "Opted Out": "FALSE", "_row_index": -1})

    engine = ConversationEngine()
    agent = VoiceAgent(conversation_engine=engine, use_mic=use_mic)
    print(f"Calling: {lead.name} @ {lead.company}")
    result = agent.make_call(lead.phone, lead)

    print("\n" + "=" * 60)
    print("CALL COMPLETE")
    print("=" * 60)
    print(json.dumps(result, indent=2))
    print()


def run_dry_run():
    print("\n" + "=" * 60)
    print("SALES VOICE AGENT - DRY RUN")
    print("=" * 60)
    print("\nSimulating calls without actual voice/LLM.\n")

    lead_manager = LeadManager()
    updater = CRMUpdater(lead_manager)
    pending = lead_manager.get_pending_leads()

    for lead in pending:
        print(f"\n--- Simulating call to {lead.name} ({lead.phone}) ---")
        print(f"  Company: {lead.company}")
        print(f"  Lead ID: {lead.id}")
        print(f"  Status: {lead.status}")
        print(f"  Opted Out: {lead.opted_out}")

        result = {
            "lead_id": lead.id,
            "outcome": "interested",
            "summary": f"Dry run: {lead.name} expressed interest in workflow automation.",
            "requirements": "Automated invoice processing",
            "objections": "None raised",
            "next_steps": "Send product demo link",
            "follow_up": "2026-07-10",
            "qualification": "yes",
            "meeting_date": "2026-07-14 10:00",
        }

        updater.update_after_call(lead, result)
        print(f"  ✓ Updated CRM: {result['outcome']}")

    print(f"\n{'='*60}")
    print(f"DRY RUN COMPLETE - {len(pending)} leads processed")
    print(f"{'='*60}\n")
    print("Check data/leads.xlsx for updated records.")


if __name__ == "__main__":
    main()

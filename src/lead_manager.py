import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional
from .utils import load_settings

class Lead:
    def __init__(self, row: dict):
        self.id = row.get("Lead ID")
        self.name = row.get("Name", "")
        self.phone = row.get("Phone Number", "")
        self.email = row.get("Email", "")
        self.company = row.get("Company", "")
        self.status = row.get("Call Status", "Pending")
        self.qualification = row.get("Lead Qualification", "")
        self.summary = row.get("Conversation Summary", "")
        self.requirements = row.get("Customer Requirements", "")
        self.objections = row.get("Objections Raised", "")
        self.follow_up = row.get("Follow-up Date", "")
        self.meeting_date = row.get("Meeting Date & Time", "")
        self.last_contacted = row.get("Last Contacted Timestamp", "")
        self.opted_out = str(row.get("Opted Out", "FALSE")).strip().upper() == "TRUE"
        self.notes = row.get("Notes", "")
        self._row_index = row.get("_row_index", -1)

    @property
    def is_pending(self) -> bool:
        return self.status.strip().lower() == "pending"

    @property
    def is_opted_out(self) -> bool:
        return self.opted_out

    @property
    def should_call(self) -> bool:
        return self.is_pending and not self.is_opted_out

    def __repr__(self):
        return f"Lead(id={self.id}, name={self.name}, company={self.company}, status={self.status})"


class LeadManager:
    def __init__(self, file_path: Optional[str] = None):
        settings = load_settings()
        self.file_path = Path(file_path or settings["excel"]["file_path"])
        self.sheet_name = settings["excel"]["sheet_name"]
        self._df: Optional[pd.DataFrame] = None

    def load_leads(self) -> list[Lead]:
        self._df = pd.read_excel(self.file_path, sheet_name=self.sheet_name)
        self._df = self._df.fillna("")
        self._df["_row_index"] = range(len(self._df))
        leads = [Lead(row) for _, row in self._df.iterrows()]
        print(f"[LeadManager] Loaded {len(leads)} leads from {self.file_path}")
        return leads

    def get_pending_leads(self) -> list[Lead]:
        all_leads = self.load_leads()
        pending = [l for l in all_leads if l.should_call]
        print(f"[LeadManager] {len(pending)} pending leads to call")
        return pending

    def update_lead(self, lead: Lead):
        if self._df is None:
            self.load_leads()

        idx = lead._row_index
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        updates = {
            "Call Status": lead.status,
            "Lead Qualification": lead.qualification,
            "Conversation Summary": lead.summary,
            "Customer Requirements": lead.requirements,
            "Objections Raised": lead.objections,
            "Follow-up Date": lead.follow_up,
            "Meeting Date & Time": lead.meeting_date,
            "Last Contacted Timestamp": now,
        }

        for col, value in updates.items():
            if col in self._df.columns:
                self._df.at[idx, col] = value

        self._save()
        print(f"[LeadManager] Updated lead {lead.id} ({lead.name})")

    def _save(self):
        with pd.ExcelWriter(self.file_path, engine="openpyxl", mode="w") as writer:
            self._df.to_excel(writer, sheet_name=self.sheet_name, index=False)
        print(f"[LeadManager] Saved to {self.file_path}")

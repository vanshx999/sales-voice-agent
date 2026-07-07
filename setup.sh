#!/bin/bash
set -e

echo "=========================================="
echo "  Sales Voice Agent - Setup"
echo "=========================================="

# Check Python
PYTHON=$(which python3)
if [ -z "$PYTHON" ]; then
    echo "Error: Python 3 not found. Install Python 3.10+ first."
    exit 1
fi
echo "✓ Python: $($PYTHON --version)"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv venv
fi

source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Setup .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✓ Created .env file - edit it with your API keys"
else
    echo "✓ .env already exists"
fi

# Verify Excel file
if [ ! -f "data/leads.xlsx" ]; then
    echo "Creating sample leads file..."
    python3 -c "
import openpyxl
wb = openpyxl.Workbook()
ws = wb.active
ws.title = 'Leads'
headers = ['Lead ID','Name','Phone Number','Email','Company','Call Status','Lead Qualification','Conversation Summary','Customer Requirements','Objections Raised','Follow-up Date','Meeting Date & Time','Last Contacted Timestamp','Opted Out','Notes']
ws.append(headers)
for i, l in enumerate([
    [1,'John Smith','+15551234567','john@acme.com','Acme Corp','Pending'],
    [2,'Sarah Johnson','+15559876543','sarah@beta.io','Beta Industries','Pending'],
    [3,'Mike Chen','+15555551234','mike@gamma.co','Gamma LLC','Pending'],
], 1):
    ws.append(l + ['']*(len(headers)-len(l)))
wb.save('data/leads.xlsx')
"
    echo "✓ Sample leads.xlsx created"
fi

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Edit .env with your API keys"
echo "  2. Edit config/knowledge_base.yaml with your company info"
echo "  3. Edit data/leads.xlsx with your leads"
echo ""
echo "Run:"
echo "  source venv/bin/activate"
echo "  python -m src.main --demo       # Demo mode"
echo "  python -m src.main --all        # Process all leads"
echo ""

# NammaSahaya — Complete Citizen Service Discovery Platform

A final-year project for discovering Karnataka government services. It provides multilingual search, typo-tolerant matching, direct official application links, status links, document guidance, step-by-step guidance, eligibility guidance, scam checking, login, backend search/activity history and saved application references.

## Important
NammaSahaya is NOT an official Government of Karnataka portal. It links users to official portals for the actual application/payment/submission. Government rules, deadlines, fees, documents and eligibility can change.

## Run on Windows
```cmd
cd C:\path\to\NammaSahaya_Complete_Citizen_Service_Platform
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Open `http://127.0.0.1:8000` in Chrome.

## Features
- 50+ government/service records
- English + Kannada interface
- typo tolerant search (`schlorship` finds scholarship)
- direct official Apply/Open links
- direct Status/Track links
- documents, steps, eligibility and help/contact for each record
- universal official-domain search for services outside the catalog
- login/register
- backend search history
- backend activity history (search, view, apply click, status click, saved reference)
- saved application/acknowledgement references
- civic grievance guide
- scam checker
- voice search in supported Chrome browsers

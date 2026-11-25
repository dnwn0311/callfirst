"""Care-connection checklist.

Rules, not the model, decide which actions to suggest; each action names the data that triggered it
and the public guidance it comes from. The model only decides call order. Nothing here lowers
anyone's priority: red-flag symptoms always mean emergency care, whatever the score.
"""
from __future__ import annotations

SOURCES = {
    "RED": {
        "name": "AHRQ Re-Engineered Discharge (RED) Toolkit",
        "url": "https://www.ahrq.gov/patient-safety/settings/hospital/red/toolkit/index.html",
    },
    "RED5": {
        "name": "AHRQ RED Tool 5: postdischarge follow-up phone call (call 2 to 3 days after discharge)",
        "url": "https://www.ahrq.gov/patient-safety/settings/hospital/red/toolkit/redtool5.html",
    },
    "ADA": {
        "name": "ADA Standards of Care in Diabetes (section on diabetes care in the hospital)",
        "url": "https://professional.diabetes.org/standards-of-care",
    },
    "TCM": {
        "name": "CMS Transitional Care Management (contact within 2 business days, visit within 7 or 14 days)",
        "url": "https://www.cms.gov/medicare/payment/fee-schedules/physician-fee-schedule/care-management/transitional-care-management-services",
    },
}

SAFETY_NOTE = (
    "Red-flag symptoms (chest pain, trouble breathing, fainting, new confusion, blood sugar that stays "
    "very low or very high) mean emergency care now, whatever the CallFirst score. A low score never means "
    "a patient does not need follow-up."
)

# Community resources by locale. These are directories to start from, not referrals;
# check eligibility and current contacts locally before use.
RESOURCES = {
    "US": [
        {"name": "Eldercare Locator (Area Agencies on Aging)", "detail": "1-800-677-1116 · meals, transport, in-home help",
         "url": "https://eldercare.acl.gov"},
        {"name": "Diabetes self-management education and support (DSMES)", "detail": "Find a recognized program",
         "url": "https://diabetes.org/tools-resources/diabetes-education-programs"},
    ],
    "KR": [
        {"name": "통합돌봄 퇴원환자 연계 (Integrated care discharge linkage)",
         "detail": "Hospital discharge coordinator works with the 시·군·구 integrated care team; nationwide since 27 March 2026",
         "url": "https://www.bokjiro.go.kr/ssis-tbu/cms/pc/news/promotion/1309483_1118.html"},
        {"name": "노인장기요양보험 (Long-term care insurance)", "detail": "National Health Insurance Service · 1577-1000",
         "url": "https://www.longtermcare.or.kr"},
        {"name": "보건소 방문건강관리 (Public health center home visits)", "detail": "Local public health center",
         "url": "https://www.mohw.go.kr"},
        {"name": "보건복지상담센터 (Welfare call center)", "detail": "Phone 129", "url": "https://www.129.go.kr"},
    ],
}


def checklist(features: dict, in_call_list: bool) -> list[dict]:
    f = features
    items = []

    def add(key, title, why, source):
        items.append({"id": key, "title": title, "why": why, "source": source})

    if f["discharge_to"] == "left against advice":
        add("ama", "Reach out today: patient left against medical advice",
            "Discharged: left against advice", "RED")
    if in_call_list:
        if f["discharge_to"] == "nursing facility":
            add("handoff", "Call the receiving facility's nurse within 2-3 days",
                "Discharged to a nursing facility", "RED5")
        else:
            add("call", "Follow-up phone call 2-3 days after discharge",
                "In today's call list", "RED5")
    prior_in = int(f["number_inpatient"])
    prior_er = int(f["number_emergency"])
    if prior_in >= 1 or prior_er >= 1:
        parts = []
        if prior_in:
            parts.append(f"{prior_in} admission{'s' if prior_in > 1 else ''}")
        if prior_er:
            parts.append(f"{prior_er} ER visit{'s' if prior_er > 1 else ''}")
        add("visit", "Book the follow-up visit before the patient leaves (aim: within 7 days)",
            " and ".join(parts) + " in the past year", "TCM")
    changes = int(f["n_dose_changes"])
    if changes or f["med_change"] == "yes" or f["num_medications"] >= 20:
        why = []
        if f["insulin"] in ("up", "down"):
            why.append(f"insulin dose went {f['insulin']}")
        if changes:
            why.append(f"{changes} diabetes dose change{'s' if changes > 1 else ''}")
        if f["num_medications"] >= 20:
            why.append(f"{int(f['num_medications'])} medications this stay")
        add("meds", "Medication reconciliation: confirm the patient knows what changed",
            "; ".join(why) or "diabetes medicines changed", "RED")
    if f["a1c"] in (">8", ">7") or f["max_glu"] in (">200", ">300"):
        why = [f"HbA1c {f['a1c']}"] if f["a1c"] in (">8", ">7") else []
        if f["max_glu"] in (">200", ">300"):
            why.append(f"max glucose {f['max_glu']} mg/dL")
        add("glucose", "Diabetes follow-up and glucose plan; offer diabetes education",
            ", ".join(why), "ADA")
    if f["age_years"] >= 75 and f["discharge_to"] in ("home", "home with home health"):
        add("home", "Check support at home (meals, mobility, help with medicines); refer to community care",
            f"Age {int(f['age_years']) - 5}-{int(f['age_years']) + 4}, going {f['discharge_to']}", "RED")
    return items

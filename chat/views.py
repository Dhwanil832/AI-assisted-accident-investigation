import json
import re 
import ollama
from datetime import datetime
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import IncidentReport, UnfinishedReport, UploadedFile
from .unfinished_handler import UnfinishedReportHandler
from collections import Counter
from chat.rag_utils import load_faiss_index
load_faiss_index()
from chat.rag_utils import search_similar_incidents
from django.contrib.auth.decorators import login_required
from .models import IncidentReport, UnfinishedReport
from accounts.models import CustomUser 
from django.contrib.auth.decorators import user_passes_test



SIF_CASE_OPTIONS = [
    "Non-SIF",
    "SIFc",  # candidate
    "SIFp",  # proposed
    "SIFa",  # actual
]

LIFE_SAVING_RULES_OPTIONS = [
    "Bypassing Safety Controls",
    "Confined Space",
    "Driving",
    "Fire",
    "Fitness for Duty",
    "Hazardous Energy Control",
    "Line of Fire",
    "Molten Metal",
    "Safe Mechanical Lifting",
    "Take 5",
    "Work at Elevation"
]

DAMAGE_AMOUNT_OPTIONS = [
    "$0 - $24,999",
    "$25,000 - $99,999",
    "$100,000 - $499,999",
    "$500,000 - $999,999",
    "$1,000,000+"
]

ACTIVITY_TYPE_OPTIONS = [
    "Routine Operations",
    "Maintenance",
    "Construction",
    "Emergency Response",
    "Testing/Inspection",
    "Transportation",
    "Material Handling",
    "Cleaning/Housekeeping",
    "Office Work",
    "Training"
]

INCIDENT_ACTIVITY_OPTIONS = [
    "Operating Machinery / Equipment",
    "Manual Material Handling",
    "Using Hand Tools",
    "Using Power Tools",
    "Driving/Operating Vehicle",
    "Walking/Moving",
    "Climbing/Descending",
    "Lifting/Carrying",
    "Welding/Cutting",
    "Chemical Handling"
]

INCIDENT_AGENT_OPTIONS = [
    "Molten Metal, Slag",
    "Heavy Equipment",
    "Hand Tools",
    "Power Tools",
    "Vehicles",
    "Electrical Equipment",
    "Chemicals",
    "Structural Components",
    "Material Handling Equipment",
    "Pressure Systems"
]

SKIP_PHRASES = [
    "skip", 
    "skip this", 
    "not sure", 
    "i don't know", 
    "leave it blank",
    "prefer not to say", 
    "i’ll come back to this", 
    "can't say", 
    "no idea", 
    "don't know", 
    "na", 
    "n/a"
]

widget_map = {
    "shift": "shift-picker",
    "person_type": "person-type-picker",
    "severity": "severity-picker",
    "accident_type": "accident-type-picker",
    "accident_agent": "accident-agent-picker",
    "injury_type": "injury-type-picker",
    "injury_agent": "injury-agent-picker",
    "sif_case": "sif-case-picker",
    "life_saving_rules": "life-saving-rules-picker",
    "damage_amount": "damage-amount-picker",
    "activity_type": "activity-type-picker",
    "incident_activity": "incident-activity-picker",
    "incident_agent": "equipment-incident-agent-picker"
}

def is_admin(user):
    return user.is_authenticated and user.role == 'admin'

def guess_sif_case_from_text(text: str):
    text_lower = text.lower()
    if "candidate" in text_lower or "candid" in text_lower:
        return "SIFc"
    elif "proposed" in text_lower or "proposal" in text_lower:
        return "SIFp"
    elif "actual" in text_lower or "implemented" in text_lower or "in place" in text_lower:
        return "SIFa"
    else:
        return ""
    
def determine_shift(time_str: str):
    try:
        hour = int(time_str.split(":")[0])
    except:
        return ""

    if 0 <= hour < 8:
        return "Shift A"
    elif 8 <= hour < 16:
        return "Shift B"
    else:
        return "Shift C"
    
def required_sections(incident_type: str):
    sections = ["basic_info"]
    if incident_type == "Personal Injuries":
        sections.append("injury_data")
    elif incident_type == "Near Miss":
        sections.append("near_miss_data")
    elif incident_type == "Equipment Damage":
        sections.append("equipment_damage_data")
    return sections


# Required fields for incident reports
REQUIRED_FIELDS = {
    "basic_info": ["datetime","shift","location", "person_involved", "person_type", "incident_type", "actions_taken", "severity"],
    "injury_data": ["accident_type", "accident_agent", "injury_type", "injury_agent","sif_case"],
    "near_miss_data": ["sif_case", "life_saving_rules"],
    "equipment_damage_data": ["damage_amount", "activity_type", "incident_activity", "incident_agent"]
}

# Define the options at the top of the file
ACCIDENT_AGENT_OPTIONS = [
    "Action of Employee",
    "AGV (Automated Guided Vehicle)",
    "Asbestos",
    "Attaching a curtain to the rib",
    "Automated Welder (Pedestal/Spot)",
    "Banding/Wrapping Materials&Equipt",
    "Beam",
    "Belt",
    "Bin",
    "Bins/Totes/Racks or Gaylords",
    "Blower Fan (Heater/AC)",
    "Bulldozers",
    "Bumper Handrail",
    "Burning/Welding, Lancing Equipment",
    "Cable",
    "Chainfall, Come-a-long",
    "Chemicals Other",
    "Chemicals, Corrosive",
    "Chemicals, Toxic",
    "Chisel"
]
INCIDENT_TYPE_OPTIONS = [
    "Personal Injuries",
    "Near Miss",
    "Equipment Damage"
]


# System prompt to guide the LLM's response
SYSTEM_PROMPT = """

You are an AI workplace safety assistant designed to help users fill out structured incident reports accurately and reliably.

Your job is to interact with the user in a multi-turn conversation and extract specific fields of information based on their inputs. You will always receive three inputs:
1. The current state of the report in JSON format (including all filled and unfilled fields).
2. The user’s latest message.
3. (Optional) Context from similar past incidents (RAG context).

Your responsibilities:
- The user may express field updates casually or indirectly. Handle the following variations:
    Examples:
    - “critical” → update "severity" to "critical"
    - “severity: moderate” → update severity
    - “line 4” (when location is still blank) → set "location"
    - “contractor” (if person_type is missing) → update person_type

    Your job is to:
    - Interpret natural language for field updates
    - Compare against the current report state
    - Update only fields where you are confident
    - Leave all others unchanged or blank

- Users may choose to skip questions they cannot answer or prefer not to answer. They may express this intent in various ways, such as:

    - "skip this"
    - "not sure"
    - "I don’t know"
    - "leave it blank"
    - "I’ll come back to this"
    - "prefer not to say"
    - "I'm unsure"
    - "can't say"
    - "no idea"

- If the user's message clearly indicates that they want to skip or do not know the answer:
    - Do not guess or assume the value.
    - Leave the corresponding field empty (as an empty string).
    - Politely acknowledge the skip and continue with the next missing field.

- Carefully read the current state of the report and determine what information is already provided.
- Read the user’s latest message and determine if it provides:
    - A new field value.
    - A correction to an existing field.
    - A clarification or partial information.
- NEVER repeat questions about fields that are already filled unless the user explicitly asks to change them.
- DO NOT fabricate or assume information. If the user's message is unclear or ambiguous for a required field, return that field as an empty string.
- DO NOT hallucinate values. If no value is explicitly mentioned or clearly implied, leave it empty.
- If the user provides a partial answer (e.g., just “critical”), infer the most likely field (e.g., severity) ONLY IF it is strongly indicated by context.
- Always follow the structure provided and return ONLY a valid JSON object matching the expected schema.
- Do NOT include explanations, summaries, or helper text in your response.

You are expected to extract and return the following fields (grouped logically):

basic_info:
- datetime (Format: YYYY-MM-DD HH:MM in 24-hour)
- shift (inferred from time or if stated)
- location (specific place in the workplace)
- person_involved (names or roles of people involved)
- person_type (Employee, Contractor; blank if unknown)
- incident_type (Personal Injuries, Near Miss, Equipment Damage)
- actions_taken (precise actions taken in response)
- severity (minor, moderate, severe, critical)

injury_data (if incident_type is "Personal Injuries"):
- accident_type
- accident_agent
- injury_type
- injury_agent
- sif_case (choose from: Non-SIF, SIFc, SIFp, SIFa)

near_miss_data (if incident_type is "Near Miss"):
- sif_case (choose from: Non-SIF, SIFc, SIFp, SIFa)
- life_saving_rules (select from known safety rules)

equipment_damage_data (if incident_type is "Equipment Damage"):
- damage_amount (e.g., "$0 - $24,999")
- activity_type (the type of task being done)
- incident_activity (what exactly was occurring)
- incident_agent (tools or equipment involved)

Always return your output as:

{
    "basic_info": {
        "date": "",
        "time": "",
        "shift": "",
        "location": "",
        "person_involved": "",
        "person_type": "",
        "incident_type": "",
        "actions_taken": "",
        "severity": ""
    },
    "injury_data": {
        "accident_type": "",
        "accident_agent": "",
        "injury_type": "",
        "injury_agent": "",
        "sif_case": ""
    },
    "near_miss_data": {
        "sif_case": "",
        "life_saving_rules": ""
    },
    "equipment_damage_data": {
        "damage_amount": "",
        "activity_type": "",
        "incident_activity": "",
        "incident_agent": ""
    }
}

Your output MUST be a valid JSON object. DO NOT add comments, explanations, summaries, or clarification messages outside the JSON. If you're unsure, leave fields empty.

If the report already appears mostly complete, begin preparing a summary or ask for final confirmation.

"""

# Dictionary to track user sessions
USER_SESSIONS = {}

def save_chat_message(session_data, message, is_user=False):
    """Save chat message to session history"""
    if "chatHistory" not in session_data:
        session_data["chatHistory"] = []
    session_data["chatHistory"].append({
        "content": message,
        "isUser": is_user,
        "timestamp": datetime.now().isoformat()
    })

@csrf_exempt
def chatbot_api(request):
    session_id = request.GET.get("session_id", "default")

    # Handle GET request for initial greeting
    if request.method == "GET" and not request.GET.get("check_unfinished") and not request.GET.get("list_unfinished"):
        # Initialize session data if not already present
        if session_id not in USER_SESSIONS:
            USER_SESSIONS[session_id] = {
                "step": "ask_user_info",  # Start with asking user info
                "user_info": {},
                "report": {},
                "chatHistory": []
            }
            session_data = USER_SESSIONS[session_id]
        else:
            session_data = USER_SESSIONS[session_id]

        # Check if we need user info
        if not session_data.get("user_info"):
            prompt = "Welcome! Before we start, please enter your name and job title."
            save_chat_message(session_data, prompt)
            return JsonResponse({
                "response": prompt,
                "show_widget": "user-info-widget"
            })

        # Normal greeting flow
        initial_greeting = "Hi, I'm your Safety Chatbot. How can I help you?"
        save_chat_message(session_data, initial_greeting)
        return JsonResponse({
            "response": initial_greeting,
            "show_widget": "initial-options",
            "options": [
                "Personal Injuries",
                "Near Miss",
                "Equipment Damage",
                "Report an incident"
            ]
        })

    # Handle GET request to list all unfinished reports
    if request.method == "GET" and request.GET.get("list_unfinished"):
        reports = UnfinishedReportHandler.get_all_unfinished_reports()
        return JsonResponse({
            "unfinished_reports": reports
        })

    # Handle POST request to resume another user's report
    if request.method == "POST" and request.GET.get("resume_report"):
        data = json.loads(request.body)
        target_session_id = data.get("session_id")
        if target_session_id:
            report_data = UnfinishedReportHandler.get_unfinished_report(target_session_id)
            if report_data:
                USER_SESSIONS[session_id] = report_data
                
                # 检查报告中缺失的字段并继续对话
                current_report = report_data.get("report", {})
                basic_info = current_report.get("basic_info", {})
                incident_type = basic_info.get("incident_type")

                # 确定下一个需要填写的字段
                next_question = None
                show_widget = None

                # 检查基本信息字段
                if not basic_info.get("datetime"):
                    next_question = "When did the incident occur?"
                    show_widget = "datetime-picker"
                elif not basic_info.get("location"):
                    next_question = "Where did this incident occur?"
                elif not basic_info.get("person_involved"):
                    next_question = "Who was involved in this incident?"
                elif not basic_info.get("person_type"):
                    next_question = "Is the person involved an Employee or Contractor?"
                    show_widget = "person-type-picker"
                elif not basic_info.get("severity"):
                    next_question = "Please select the severity level."
                    show_widget = "severity-picker"
                elif not basic_info.get("actions_taken"):
                    next_question = "What actions were taken?"
                    show_widget = None

                # 根据事故类型检查特定字段
                elif incident_type == "Personal Injuries":
                    injury_data = current_report.get("injury_data", {})
                    if not injury_data.get("accident_type"):
                        next_question = "Please select the accident type."
                        show_widget = "accident-type-picker"
                    elif not injury_data.get("accident_agent"):
                        next_question = "Please select what caused the accident (accident agent)."
                        show_widget = "accident-agent-picker"
                    elif not injury_data.get("injury_type"):
                        next_question = "Please select the type of injury."
                        show_widget = "injury-type-picker"
                    elif not injury_data.get("injury_agent"):
                        next_question = "Please select what caused the injury (injury agent)."
                        show_widget = "injury-agent-picker"
                    elif not injury_data.get("sif_case"):
                        next_question = "Is this incident a SIF case? Please select."
                        show_widget = "sif-case-picker"

                elif incident_type == "Near Miss":
                    near_miss_data = current_report.get("near_miss_data", {})
                    if not near_miss_data.get("sif_case"):
                        next_question = "For this near miss incident, is it a SIF case? Please select."
                        show_widget = "near-miss-sif-case-picker"
                    elif not near_miss_data.get("life_saving_rules"):
                        next_question = "Which Life Saving Rules were relevant to this near miss?"
                        show_widget = "life-saving-rules-picker"

                elif incident_type == "Equipment Damage":
                    equipment_data = current_report.get("equipment_damage_data", {})
                    if not equipment_data.get("damage_amount"):
                        next_question = "Please select the amount of damage."
                        show_widget = "damage-amount-picker"
                    elif not equipment_data.get("activity_type"):
                        next_question = "What type of activity was being performed?"
                        show_widget = "activity-type-picker"
                    elif not equipment_data.get("incident_activity"):
                        next_question = "What specific activity was occurring during the incident?"
                        show_widget = "incident-activity-picker"
                    elif not equipment_data.get("incident_agent"):
                        next_question = "What was the primary agent involved in the incident?"
                        show_widget = "equipment-incident-agent-picker"

                # 如果所有必填字段都已填写，进入确认阶段
                if not next_question:
                    next_question = "Thanks for the information. Here's what I have so far, Please confirm if this is correct:"
                    report_data["step"] = "confirm_extracted"

                return JsonResponse({
                    "response": "Successfully loaded the selected report. You can now continue editing it.",
                    "restored_data": report_data,
                    "next_question": next_question,
                    "show_widget": show_widget
                })
        return JsonResponse({
            "error": "Report not found or invalid session ID"
        }, status=400)

    session_data = USER_SESSIONS[session_id]
    if not session_data:
        USER_SESSIONS[session_id] = {
            "step": "greet",
            "report": {},
            "chatHistory": []
        }
        session_data = USER_SESSIONS[session_id]

    if request.method == "GET" and request.GET.get("check_unfinished"):
        unfinished_report = UnfinishedReportHandler.get_unfinished_report(session_id)
        if unfinished_report:
            return JsonResponse({
                "has_unfinished": True,
                "unfinished_data": unfinished_report
            })
        return JsonResponse({"has_unfinished": False})

    if request.method == "POST" and request.GET.get("handle_unfinished"):
        data = json.loads(request.body)
        if data.get("continue"):
            unfinished_report = UnfinishedReportHandler.get_unfinished_report(session_id)
            if unfinished_report:
                USER_SESSIONS[session_id] = unfinished_report
                UnfinishedReportHandler.delete_unfinished_report(session_id)
                return JsonResponse({
                    "response": "Welcome back! Continuing your previous report...",
                    "restored_data": unfinished_report
                })
        else:
            UnfinishedReportHandler.delete_unfinished_report(session_id)
            USER_SESSIONS[session_id] = {"step": "greet", "report": {}}
            return JsonResponse({
                "response": "Starting a new report...",
                "show_widget": None
            })
    
    if request.method == "POST" and request.GET.get("remove_report"):
        data = json.loads(request.body)
        sid = data.get("session_id")
        user = data.get("username")
        pwd  = data.get("password")
        # 简单示例：用户名/密码硬编码，生产环境请用 Django Auth 或环境变量
        if user == "admin" and pwd == "admin123":
            UnfinishedReportHandler.delete_unfinished_report(sid)  # :contentReference[oaicite:2]{index=2}&#8203;:contentReference[oaicite:3]{index=3}
            return JsonResponse({"success": True})
        else:
            return JsonResponse({"success": False, "error": "Invalid credentials"}, status=401)

    # Handle POST requests
    if request.method == "POST":
        try:
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError as e:
                print("Bad JSON in request.body:", str(e))
                return JsonResponse({"error": "Invalid JSON payload"}, status=400)

            # Support both message and button-only input
            message = data.get("message")
            user_input = ""

            if message is not None:
                if not isinstance(message, str):
                    print("Invalid 'message' type in request:", data)
                    return JsonResponse({"error": "'message' must be a string"}, status=400)
                user_input = message.strip()

                        
            button_choice = data.get("button_choice")
            current_data = data.get("current_data", {})

            # Save user message to chat history
            save_chat_message(session_data, user_input, is_user=True)
            
            # Update session data with current_data if available
            if current_data:
                for section in ["basic_info", "injury_data", "near_miss_data", "equipment_damage_data"]:
                    if section in current_data and current_data[section]:
                        if section not in session_data["report"]:
                            session_data["report"][section] = {}
                        session_data["report"][section].update(current_data[section])

            # Save current state as unfinished if not completed
            if session_data["step"] != "completed":
                UnfinishedReportHandler.save_unfinished_report(session_id, {
                    "step": session_data["step"],
                    "report": session_data["report"],
                    "chatHistory": session_data.get("chatHistory", [])
                },request.user)

            print("Received user input:", user_input)
            print("Current session data:", session_data)
            
            if user_input.lower() in ["hi", "hello", "hey", "good morning", "good afternoon"]:
                return JsonResponse({
                    "response": "Hello! How can I help you?",
                    "show_widget": None
                })
            # === STEP 1.1: Always send message to LLM ===
            if session_data["step"] == "extract_fields" and user_input:
                try:
                    rag_context = ""
                    if session_data.get("rag_retrieved_incidents"):
                        rag_context = "Here are some similar past incidents and actions taken:\n"
                        for idx, inc in enumerate(session_data["rag_retrieved_incidents"], 1):
                            description = inc.get("description") or inc.get("Unnamed: 35") or inc.get("Unnamed: 37") or ""
                            if description:
                                rag_context += f"- Description: {description}\n"
                            actions_taken = inc.get("actions_taken") or inc.get("Unnamed: 41") or ""
                            if actions_taken:
                                rag_context += f"- Actions Taken: {actions_taken}\n"
                            location = inc.get("location") or inc.get("Unnamed: 34") or ""
                            if location:
                                rag_context += f"- Location: {location}\n"
                            sif_case = inc.get("sif_case") or inc.get("Unnamed: 55") or ""
                            if sif_case:
                                rag_context += f"- SIF Case: {sif_case}\n"
                            rag_context += "\n"

                    report_state_json = json.dumps(session_data.get("report", {}), indent=2)
                    llm_user_message = (
                        f"{rag_context}\n"
                        f"Here is the current report state:\n{report_state_json}\n\n"
                        f"User message: {user_input}\n"
                        f"Please extract updates and identify missing fields accordingly."
                    )

                    response = ollama.chat(
                        model="qwen2.5",
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": llm_user_message},
                        ]
                    )
                    extracted_content = response["message"]["content"]
                    print("LLM Response:", extracted_content)

                    json_match = re.search(r"\{.*\}", extracted_content, re.DOTALL)
                    if json_match:
                        extracted_json = json.loads(json_match.group(0))

                        for section in ["basic_info", "injury_data", "near_miss_data", "equipment_damage_data"]:
                            if section not in session_data["report"]:
                                session_data["report"][section] = {}
                            if section in extracted_json:
                                for key, value in extracted_json[section].items():
                                    if section == "basic_info" and key == "incident_type" and session_data["report"][section].get("incident_type"):
                                        continue
                                    if isinstance(value, str) and value and "?" not in value:
                                        if key in ["incident_type", "actions_taken"] and session_data["report"][section].get(key):
                                            continue
                                        existing_value = session_data["report"][section].get(key)
                                        if not existing_value or (existing_value and value != existing_value):
                                            session_data["report"][section][key] = value
                                            print(f"Updated {section}.{key} to: {value}")

                    incident_type = session_data["report"]["basic_info"].get("incident_type", "")
                    required_sections_list = required_sections(incident_type)

                    # Check if user wants to skip a field
                    if user_input.lower().strip() in SKIP_PHRASES:
                        for section in required_sections_list:
                            for field in REQUIRED_FIELDS.get(section, []):
                                if not session_data["report"].get(section, {}).get(field):
                                    session_data["report"].setdefault(section, {})[field] = ""
                                    return JsonResponse({
                                        "response": f"Okay, I've skipped the {field.replace('_', ' ').title()}.",
                                        "extracted": session_data["report"],
                                        "show_widget": None
                                    })

                    # Fallback: ask for the next missing field
                    for section in required_sections_list:
                        for field in REQUIRED_FIELDS.get(section, []):
                            if not session_data["report"].get(section, {}).get(field):
                                field_label = field.replace("_", " ").title()
                                return JsonResponse({
                                    "response": f"Thanks, I’ve noted that. Could you please provide the {field_label}?",
                                    "extracted": session_data["report"],
                                    "show_widget": widget_map.get(field, None)
                                })

                    # If no missing field was found — everything is complete
                    session_data["step"] = "confirm_extracted"

                    return JsonResponse({
                        "response": "Thanks for the information. Here's what I have so far, please confirm if this is correct:",
                        "extracted": session_data["report"],
                        "show_widget": "confirm-buttons"
                    })


                except Exception as e:
                    print(f"LLM block error: {str(e)}")

            if session_data["step"] == "greet" and button_choice:
                if button_choice in INCIDENT_TYPE_OPTIONS:
                    # If one of the predefined incident types was selected
                    if "basic_info" not in session_data["report"]:
                        session_data["report"]["basic_info"] = {}
                    session_data["report"]["basic_info"]["incident_type"] = button_choice
                    session_data["step"] = "extract_fields"
                    response = "Got it! Please describe the incident in detail."
                    save_chat_message(session_data, response)
                    return JsonResponse({"response": response})
                elif button_choice == "Report an incident":
                    # Continue with the regular flow
                    session_data["step"] = "extract_fields"
                    response = "Got it! Please describe the incident in detail."
                    save_chat_message(session_data, response)
                    return JsonResponse({"response": response})


            elif session_data["step"] == "confirm_extracted":
                if user_input.lower() in ["yes", "confirm"]:  
                    session_data["step"] = "summary"
                    summary_story = generate_summary(session_data["report"])

                    # 仅当 Personal Injuries 时附加伤害详情
                    if session_data['report']['basic_info'].get('incident_type') == "Personal Injuries":
                        summary_story += (
                            "\n\nInjury Details:\n"
                            f"- Accident Type: {session_data['report']['injury_data'].get('accident_type', 'not specified')}\n"
                            f"- Accident Agent: {session_data['report']['injury_data'].get('accident_agent', 'not specified')}\n"
                            f"- Injury Type: {session_data['report']['injury_data'].get('injury_type', 'not specified')}\n"
                            f"- Injury Agent: {session_data['report']['injury_data'].get('injury_agent', 'not specified')}\n"
                            f"- SIF Case: {session_data['report']['injury_data'].get('sif_case', 'not specified')}\n"
                        )

                    # 仅当 Near Miss 时附加 Near‑Miss 详情
                    if session_data['report']['basic_info'].get('incident_type') == "Near Miss":
                        summary_story += (
                            "\n\nNear-Miss Details:\n"
                            f"- SIF Case: {session_data['report']['near_miss_data'].get('sif_case', 'not specified')}\n"
                            f"- Life Saving Rules: {session_data['report']['near_miss_data'].get('life_saving_rules', 'not specified')}\n"
                        )

                    # 仅当 Equipment Damage 时附加设备损坏详情
                    if session_data['report']['basic_info'].get('incident_type') == "Equipment Damage":
                        summary_story += (
                            "\n\nEquipment Damage Details:\n"
                            f"- Damage Amount: {session_data['report']['equipment_damage_data'].get('damage_amount', 'not specified')}\n"
                            f"- Activity Type: {session_data['report']['equipment_damage_data'].get('activity_type', 'not specified')}\n"
                            f"- Incident Activity: {session_data['report']['equipment_damage_data'].get('incident_activity', 'not specified')}\n"
                            f"- Incident Agent: {session_data['report']['equipment_damage_data'].get('incident_agent', 'not specified')}\n"
                        )

                    summary_story += (
                        f"\n\nActions Taken: {session_data['report'].get('basic_info', {}).get('actions_taken', 'No actions specified')}"
                    )

                    return JsonResponse({
                        "response": summary_story + "\n\nDoes this summary look correct?",
                        "summary": session_data["report"],
                        "show_widget": "summary-buttons"  
                    })
                else:
                    try:
                        corrections = json.loads(user_input)
                        session_data["report"].update(corrections)
                        return JsonResponse({
                            "response": "Thanks for the information. Here's what I have so far, Please confirm if this is correct:\n",  
                            "extracted": session_data["report"],
                            "show_widget": "confirm-buttons"
                        })
                    except:
                        corrections = user_input.lower().split(" to ")
                        if len(corrections) == 2:
                            field_to_update = corrections[0].strip().replace(" ", "_")
                            new_value = corrections[1].strip()
                            for section in ["basic_info", "injury_data", "near_miss_data", "equipment_damage_data"]:
                                if field_to_update in session_data["report"].get(section, {}):
                                    session_data["report"][section][field_to_update] = new_value
                                    return JsonResponse({
                                        "response": f"Got it! I have updated {field_to_update.replace('_',' ')} to '{new_value}'. Does this look correct now?",
                                        "extracted": session_data["report"],
                                        "show_widget": "confirm-buttons"
                                    })

                        return JsonResponse({
                            "response": "I didn't understand the correction format...",
                            "extracted": session_data["report"],
                            "show_widget": "confirm-buttons"
                        })

            elif session_data["step"] == "summary":
                if user_input.lower() in ["looks good", "yes", "confirm"]:       
                    # Get user info from request or session
                    user_info = data.get("user_info", {}) or session_data.get("user_info", {})
                    missing_fields = []
                    for section, field in required_fields:
                        if not session_data["report"].get(section, {}).get(field):
                            missing_fields.append(f"{field.replace('_', ' ').title()}")
                    if missing_fields:
                        return JsonResponse({
                            "response": f"Before submitting, please provide: {', '.join(missing_fields)}.",
                            "extracted": session_data["report"],
                            "show_widget": "summary-buttons"
                            })
                    # Save the report
                    skip_count = 0
                    for section, fields in REQUIRED_FIELDS.items():
                        for field in fields:
                            value = session_data["report"].get(section, {}).get(field)
                            if value == "" or value is None:
                                skip_count += 1

                    report = IncidentReport.objects.create(
                        report_json=session_data["report"],
                        creator_name=user_info.get("name", "Unknown"),
                        creator_job_title=user_info.get("job", "Unknown"),
                        flagged=skip_count >= 2,
                        flag_reason="Multiple fields skipped" if skip_count >= 2 else ""
                    )
                    
                    # Update all temporary files associated with this session
                    UploadedFile.objects.filter(
                        session_id=session_id,
                        is_temp=True
                    ).update(
                        incident_report=report,
                        is_temp=False
                    )
                    
                    session_data["step"] = "completed"
                    redirect_url = "admin_dashboard" if request.user.role == "admin" else "user_dashboard"

                    UnfinishedReportHandler.delete_unfinished_report(session_id)
                    # Reset the session for the next report
                    USER_SESSIONS[session_id] = {
                        "step": "greet",
                        "report": {},
                        "chatHistory": [],
                        "skip_count": 0
                    }
                    initial_greeting = "Hi, I'm your Safety Chatbot. How can I help you?"
                    save_chat_message(USER_SESSIONS[session_id], initial_greeting)
                    return JsonResponse({
                        "response": f"Your incident has been successfully recorded. Reference ID: #{report.id}. Redirecting you to your dashboard...",
                        "show_widget": None,
                        "redirect": redirect(redirect_url).url
                    })

                
                elif user_input.lower() == "add more info":
                    # Add the additional info to the report
                    if "additional_info" not in session_data["report"]:
                        session_data["report"]["additional_info"] = []
                    
                    return JsonResponse({
                        "response": "Please provide any additional information or comments you'd like to add.",
                        "show_widget": "additional-info"
                    })
                
                elif "additional_info" in session_data["report"] and session_data["step"] == "summary":
                    if user_input.lower() not in ["yes", "confirm", "looks good", "add more info"] and " to " not in user_input:
                        session_data["report"]["additional_info"].append(user_input.strip())
                        return JsonResponse({
                            "response": "I've added your comment. Does everything look good now?",
                            "extracted": session_data["report"],
                            "show_widget": "summary-buttons"
                        })

                
                else:  # "change something" or other corrections
                    corrections = user_input.lower().split(" to ")
                    if len(corrections) == 2:
                        field_to_update = corrections[0].strip().replace(" ", "_")
                        new_value = corrections[1].strip()

                        # Update the appropriate section
                        for section in ["basic_info", "injury_data", "near_miss_data", "equipment_damage_data"]:
                            if field_to_update in session_data["report"].get(section, {}):
                                session_data["report"][section][field_to_update] = new_value
                                return JsonResponse({
                                    "response": f"Got it! I have updated {field_to_update.replace('_', ' ')} to '{new_value}'. Does everything look correct now?",
                                    "extracted": session_data["report"],
                                    "show_widget": "summary-buttons"
                                })

                    return JsonResponse({
                        "response": "Try saying 'location to warehouse' or 'severity to critical' one thing at a time.",
                        "extracted": session_data["report"],
                        "show_widget": "summary-buttons"
                    })
                

            if session_data["step"] == "completed":
                UnfinishedReportHandler.delete_unfinished_report(session_id)
                # Reset the session for the next report
                USER_SESSIONS[session_id] = {
                    "step": "greet",
                    "report": {},
                    "chatHistory": []
                }
                initial_greeting = "Hi, I'm your Safety Chatbot. How can I help you?"
                save_chat_message(USER_SESSIONS[session_id], initial_greeting)
                return JsonResponse({
                    "response": f"Your incident has been successfully recorded. Reference ID: #{report.id}. If you need to report another issue, just let me know!",
                    "show_widget": "initial-options",
                    "options": [
                        "Personal Injuries",
                        "Near Miss",
                        "Equipment Damage",
                        "Report an incident"
                    ]
                })
            # Add handling for user info step
            if session_data["step"] == "ask_user_info":
                try:
                    # Try to parse as JSON first
                    user_info = json.loads(user_input)
                except json.JSONDecodeError:
                    # If not JSON, try comma-separated format
                    parts = [p.strip() for p in user_input.split(",")]
                    if len(parts) == 2:
                        user_info = {"name": parts[0], "job": parts[1]}
                    else:
                        return JsonResponse({
                            "response": "Please provide your name and job title in the format: name, job title",
                            "show_widget": "user-info-widget"
                        })

                if "name" in user_info and "job" in user_info:
                    session_data["user_info"] = user_info
                    session_data["step"] = "greet"
                    response = "Hi, I'm your Safety Chatbot. How can I help you?"
                    save_chat_message(session_data, response)
                    return JsonResponse({
                        "response": response,
                        "show_widget": "initial-options",
                        "options": [
                            "Personal Injuries",
                            "Near Miss",
                            "Equipment Damage",
                            "Report an incident"
                        ]
                    })
                else:
                    return JsonResponse({
                        "response": "Please provide both name and job title.",
                        "show_widget": "user-info-widget"
                    })

        except Exception as e:
            print(f"Error processing request: {str(e)}")
            import traceback
            print(traceback.format_exc())
            return JsonResponse({
                "error": str(e),
                "show_widget": None
            }, status=500)


    return JsonResponse({
        "error": "Invalid request method",
        "show_widget": None
    }, status=400)

def chatbot_ui(request):
    # Handle resume from dashboard
    if request.method == "POST" and request.GET.get("resume_report") == "true":
        session_id = request.POST.get("session_id", "default")
        report_data = UnfinishedReportHandler.get_unfinished_report(session_id)
        if report_data:
            USER_SESSIONS[session_id] = report_data
        else:
            messages.error(request, "Failed to load report.")
            return redirect("admin_dashboard" if request.user.role == "admin" else "user_dashboard")
    else:
        session_id = "default"
        if "restored_report" in request.session:
            USER_SESSIONS[session_id] = request.session.pop("restored_report")
            print(f"Restored session: {session_id}")
        elif session_id not in USER_SESSIONS or USER_SESSIONS[session_id].get("step") == "completed":
            USER_SESSIONS[session_id] = {
                "step": "greet",
                "report": {},
                "chatHistory": []
            }

    return render(request, "chat.html", {"session_id": session_id})

def get_top_actions(incident_type, location):
    print(f"[RAG] Searching for incident_type='{incident_type}' and location='{location}'")

    matching_reports = IncidentReport.objects.filter(
        report_json__basic_info__incident_type__iexact=incident_type,
        report_json__basic_info__location__iexact=location
    ).values_list('report_json', flat=True)

    print(f"[RAG] Found {len(matching_reports)} matching reports")

    actions_taken = []
    for report in matching_reports:
        try:
            print("[RAG] Raw report:", report)  # This might still be a string
            if isinstance(report, str):
                report = json.loads(report)  # Parse string if needed
            action = report.get('basic_info', {}).get('actions_taken', '')
            if action:
                actions_taken.append(action)
                print("[RAG] Extracted actions_taken:", action)
        except Exception as e:
            print("[RAG] Error parsing report:", e)

    top_actions = [action for action, _ in Counter(actions_taken).most_common(3)]
    print("[RAG] Top actions:", top_actions)

    
    return top_actions

@csrf_exempt
def upload_files(request):
    if request.method == 'POST':
        try:
            # Ensure media directory exists
            upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads', 
                                    datetime.now().strftime('%Y/%m/%d'))
            os.makedirs(upload_dir, exist_ok=True)
            
            session_id = request.GET.get('session_id', 'default')
            files = request.FILES.getlist('files[]')
            uploaded_files = []
            
            # Get current session data
            session_data = USER_SESSIONS.get(session_id, {})
            current_report = session_data.get('report', {})
            
            for file in files:
                # Create UploadedFile instance
                uploaded_file = UploadedFile.objects.create(
                    file=file,
                    original_name=file.name,
                    file_type=file.content_type,
                    session_id=session_id,
                    is_temp=True
                )
                
                # Add file reference to the current report's basic_info
                if 'basic_info' not in current_report:
                    current_report['basic_info'] = {}
                if 'attachments' not in current_report['basic_info']:
                    current_report['basic_info']['attachments'] = []
                
                current_report['basic_info']['attachments'].append({
                    'name': file.name,
                    'type': file.content_type,
                    'url': uploaded_file.file.url,
                    'id': uploaded_file.id
                })
                
                # Update session data
                session_data['report'] = current_report
                USER_SESSIONS[session_id] = session_data
                
                uploaded_files.append({
                    'name': file.name,
                    'type': file.content_type,
                    'url': uploaded_file.file.url,
                    'id': uploaded_file.id
                })
            
            return JsonResponse({
                'success': True,
                'files': uploaded_files
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({
        'success': False,
        'error': 'Invalid request method'
    }, status=400)

@csrf_exempt
def delete_file(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            file_id = data.get('file_id')
            session_id = request.GET.get('session_id', 'default')
            
            # Get the file
            uploaded_file = UploadedFile.objects.get(id=file_id, session_id=session_id)
            
            # Remove file reference from session data
            session_data = USER_SESSIONS.get(session_id, {})
            current_report = session_data.get('report', {})
            
            if 'basic_info' in current_report and 'attachments' in current_report['basic_info']:
                current_report['basic_info']['attachments'] = [
                    att for att in current_report['basic_info']['attachments']
                    if att.get('id') != file_id
                ]
                session_data['report'] = current_report
                USER_SESSIONS[session_id] = session_data
            
            # Delete the file
            uploaded_file.delete()
            
            return JsonResponse({
                'success': True
            })
            
        except UploadedFile.DoesNotExist:
            return JsonResponse({
                'success': False,
                'error': 'File not found'
            }, status=404)
        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    return JsonResponse({
        'success': False,
        'error': 'Invalid request method'
    }, status=400)

def generate_summary(report):
    basic = report.get("basic_info", {})
    summary_parts = []

    if basic.get("datetime"):
        line = f"On {basic['datetime']}"
        summary_parts.append(line + ",")

    if basic.get("shift"):
        summary_parts.append(f"during the {basic['shift']} shift,")

    if basic.get("person_involved"):
        person = f"{basic['person_involved']}"
        if basic.get("person_type"):
            person += f" ({basic['person_type']})"
        summary_parts.append(f"{person} was involved")

    if basic.get("incident_type"):
        summary_parts.append(f"in a {basic['incident_type']}")

    if basic.get("location"):
        summary_parts.append(f"at {basic['location']}.")

    if basic.get("severity"):
        summary_parts.append(f"The severity of the incident was assessed as {basic['severity']}.")

    # Add incident-specific sections
    type_ = basic.get("incident_type")
    if type_ == "Personal Injuries":
        injury = report.get("injury_data", {})
        summary_parts.append("\n\nInjury Details:")
        for field in ["accident_type", "accident_agent", "injury_type", "injury_agent", "sif_case"]:
            if injury.get(field):
                summary_parts.append(f"- {field.replace('_', ' ').title()}: {injury[field]}")
    elif type_ == "Near Miss":
        nm = report.get("near_miss_data", {})
        summary_parts.append("\n\nNear-Miss Details:")
        for field in ["sif_case", "life_saving_rules"]:
            if nm.get(field):
                summary_parts.append(f"- {field.replace('_', ' ').title()}: {nm[field]}")
    elif type_ == "Equipment Damage":
        eq = report.get("equipment_damage_data", {})
        summary_parts.append("In addition, equipment damage was reported with the following details:")
        for field in ["damage_amount", "activity_type", "incident_activity", "incident_agent"]:
            if eq.get(field):
                summary_parts.append(f"- {field.replace('_', ' ').title()}: {eq[field]}")

    if basic.get("actions_taken"):
        summary_parts.append(f"\n\nActions Taken: {basic['actions_taken']}")

    return " ".join(summary_parts).strip()




#-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
@login_required
def user_dashboard(request):
    user = request.user
    unfinished_reports = UnfinishedReport.objects.filter(user=user)
    completed_reports = IncidentReport.objects.filter(user=user)

    context = {
        "unfinished_reports": unfinished_reports,
        "completed_reports": completed_reports,
    }
    return render(request, "dashboard/user_dashboard.html", context)


@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    all_users = CustomUser.objects.all()
    user_data = []

    for user in all_users:
        unfinished = UnfinishedReport.objects.filter(session_id__startswith=user.username)
        flagged = IncidentReport.objects.filter(creator_name=user.username, flagged=True)

        user_data.append({
            "user": user,
            "unfinished": unfinished,
            "flagged": flagged
        })

    return render(request, "accounts/admin_dashboard.html", {"user_data": user_data})


@login_required
def resume_unfinished_report(request, session_id):
    # Retrieve the unfinished report and inject it into session
    report_data = UnfinishedReportHandler.get_unfinished_report(session_id)
    if report_data:
        request.session["restored_report"] = report_data
        request.session["session_id"] = session_id
        return redirect("chatbot_ui")
    else:
        messages.error(request, "Unable to resume report.")
        if request.user.role == "admin":
            return redirect("admin_dashboard")
        else:
            return redirect("user_dashboard")


@login_required
def delete_unfinished_report(request, session_id):
    UnfinishedReport.objects.filter(session_id=session_id).delete()
    if request.user.role == "admin":
        return redirect("admin_dashboard")
    else:
        return redirect("user_dashboard")

# Importing necessary libraries
from fastapi import FastAPI, Request  # FastAPI for building the webhook server
from twilio.twiml.messaging_response import MessagingResponse  # For Twilio WhatsApp response formatting
import openai  # To interact with the OpenAI API
from twilio.rest import Client
import re
def split_message_with_formatting(message, max_length=1600):
    """
    Splits a message into chunks of the specified maximum length, ensuring readability,
    and formats the content for WhatsApp-friendly output.
    
    Args:
        message (str): The original message to split.
        max_length (int): Maximum length of each chunk (default is 1600).
    
    Returns:
        list: A list of formatted message chunks.
    """
    import re
    
    def format_blood_report(report):
        """
        Formats the blood report for better readability on WhatsApp.
        """
        lines = report.split("\n")
        formatted_lines = []
        for line in lines:
            # Highlight section headers
            if "Complete Blood Test Results" in line or "---" in line:
                formatted_lines.append(f"*{line.strip()}*")  # Bold headers
            # Format test results as key-value pairs
            elif ":" in line:
                key, value = line.split(":", 1)
                formatted_lines.append(f"*{key.strip()}*: {value.strip()}")
            else:
                formatted_lines.append(line.strip())
        return "\n".join(formatted_lines)
    
    # Format specific sections if present
    match = re.search(r"Here's your blood report:\n(.*?)\n\nInsights:", message, re.S)
    if match:
        blood_report = match.group(1)
        formatted_report = format_blood_report(blood_report)
        message = message.replace(blood_report, formatted_report)
    
    # Split message while ensuring readability
    stop_words = [".", "!", "?", "\n"]  # Logical break points
    chunks = []
    current_chunk = ""
    words = re.split(r"(\s+)", message)  # Split on whitespace but keep it
    
    for word in words:
        if len(current_chunk) + len(word) > max_length:
            # Try to end at the nearest stop word
            for stop_word in stop_words:
                if stop_word in current_chunk[::-1]:  # Check if stop word is near the end
                    cut_index = current_chunk[::-1].index(stop_word[::-1]) + 1
                    cut_index = len(current_chunk) - cut_index
                    chunks.append(current_chunk[:cut_index + 1].strip())
                    current_chunk = current_chunk[cut_index + 1:]
                    break
            else:
                # If no stop word is found, break at max length
                chunks.append(current_chunk.strip())
                current_chunk = ""
        current_chunk += word
    
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks

def split_message_dynamic(message, max_length=1600):
    chunks = []
    while len(message) > max_length:
        # Find the last split point within the limit
        split_point = max_length
        while split_point > 0 and message[split_point] not in ['.','?', '!']:
            split_point -= 1
        
        # If no split point is found, split at max_length
        if split_point == 0:
            split_point = max_length
        
        # Take the chunk up to the split point
        chunks.append(message[:split_point].strip())
        message = message[split_point:].strip()

    # Add the remaining message as the last chunk
    if message:
        chunks.append(message)

    return chunks


# Initialize FastAPI app
app = FastAPI()

# Configure OpenAI API Key
openai.api_key = "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"  # Replace with your OpenAI API key
account_sid = 'ACc3b466139e779e862c4f545bd6e19d94'  # Replace with your Twilio Account SID
auth_token = '0587b58274800f397550c85b621ab921'  # Replace with your Twilio Auth Token

# Blood report data stored as a text string
blood_report = """
Name              : Mr. Neeraj Ojha
Lab Number        : 242862201
Age               : 27 Years
Gender            : Male
Referring Doctor  : Dr. V. K. Pandey
Sample Collected  : 1/8/2017, 8:21:00 AM
Sample Received   : 1/8/2017, 8:37:03 AM
Report Status     : Final
Reported On       : 1/8/2017, 6:52:30 PM

Complete Blood Test Results
---------------------------
Test Name                                Result       Units            Reference Range       Status
--------------------------------------------------------------------------------------------------
Hemoglobin                               12.00        g/dL             13.00 - 17.00         Low
Packed Cell Volume (PCV)                 37.70        %                40.00 - 50.00         Low
RBC Count                                5.79         mill/mm3         4.50 - 5.50           High
MCV (Mean Corpuscular Volume)            65.00        fL               80.00 - 100.00        Low
MCH (Mean Corpuscular Hemoglobin)        20.70        pg               27.00 - 32.00         Low
MCHC (Mean Corpuscular Hemoglobin Conc.) 31.90        g/dL             32.00 - 35.00         Slightly Low
Red Cell Distribution Width (RDW)        15.90        %                11.50 - 14.50         High
Total Leukocyte Count (TLC)              4.20         thou/mm3         4.00 - 10.00          Normal
Segmented Neutrophils                    39.60        %                40.00 - 80.00         Low
Lymphocytes                              50.30        %                20.00 - 40.00         High
Monocytes                                8.10         %                2.00 - 10.00          Normal
Eosinophils                              1.40         %                1.00 - 6.00           Normal
Basophils                                0.60         %                <2.00                 Normal
Platelet Count                           245.0        thou/mm3         150.00 - 450.00       Normal
"""

# Store session states to maintain conversation continuity
session_states = {}

@app.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Main webhook endpoint to handle incoming WhatsApp messages via Twilio.
    """
    # Extract message details from the incoming Twilio request
    client = Client(account_sid, auth_token)
    data = await request.form()
    user_message = data.get('Body', '').strip()  # User's WhatsApp message
    session_id = data.get('From', '')  # Unique ID for the user's WhatsApp number

    # Initialize session state if the user is new
    if session_id not in session_states:
        session_states[session_id] = {"context": [], "name_matched": False}

    # Retrieve current session state
    state = session_states[session_id]
    context = state["context"]

    # Handle the conversation flow
    if not state["name_matched"]:
        # If the name hasn't been matched yet
        if "name" not in state:
            response = "Hello! Could you please share your name so I can assist you?"
            state["context"].append({"role": "assistant", "content": response})
            state["name"] = ''
        else:
            user_name = user_message  # Assume the user's message is their name
            state["name"] = user_name
            if user_name.lower() == "neeraj ojha":  # Case-insensitive match with the blood report
                state["name_matched"] = True
                # Generate insights dynamically using OpenAI
                chat_prompt = f"Provide detailed medical insights based on the following blood test report:\n{blood_report}"
                chat_completion = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are a medical expert providing personalized insights on blood test reports."},
                        {"role": "user", "content": chat_prompt},
                    ],
                )
                insights = chat_completion['choices'][0]['message']['content']
                response = f"Welcome, {user_name}! Here's your blood report:\n{blood_report}\n\nInsights:\n{insights}"
                context.append({"role": "assistant", "content": response})
            else:
                response = "I'm sorry, I couldn't find your report under the name . Can you verify & provide your name again?"
                context.append({"role": "assistant", "content": response})
    else:
        # If name is already matched, handle follow-up queries
        context.append({"role": "user", "content": user_message})
        chat_completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "You are a helpful assistant answering health-related queries."}] + context
        )
        response = chat_completion['choices'][0]['message']['content']
        context.append({"role": "assistant", "content": response})

    # Update the session state with the latest context
    session_states[session_id]["context"] = context

    # Send the response back to Twilio
    try:
        messages = split_message_with_formatting(response)
        for chunk in messages:
            client.messages.create(
                from_="whatsapp:+919319837618",  # Replace with your registered WhatsApp number
                body=chunk,  # Chunk content
                to=session_id
            )
    except Exception as e:
        print("Failed to send message:", e)
    print(context)
    twilio_response = MessagingResponse()
    twilio_response.message(response)
    return str(twilio_response)

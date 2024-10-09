# Standard library imports
import json
import os
from datetime import date
from dotenv import load_dotenv
from typing import Optional
import re

# Third-party imports
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import BaseTool
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.tools import ToolException
from langchain_openai import ChatOpenAI

# Local imports
from calcom_api import create_booking, get_user_bookings, cancel_user_booking, reschedule_booking

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class CalComBookingException(Exception):
    """Custom exception for Cal.com booking errors."""
    pass

# Tool for Cal.com booking
class CalComBookingTool(BaseTool):
    name: str = "calcom_booking_tool"
    description: str = "Create a booking using Cal.com API"
    handle_tool_error: bool=True

    def _run(self, date: str, time: str, duration: int, reason: str, name: str, email: str) -> str:
        try: 
            result = create_booking(date, time, duration, reason, name, email)
            result_json = json.loads(result)
            if "error" in result_json:
                raise CalComBookingException(result_json["error"])
            return f"Booking created successfully. Booking details: {result_json}"
        except CalComBookingException as e:
            raise ToolException(f"Booking error: {str(e)}")
        except Exception as e:
            raise ToolException(f"Unknown error: {str(e)}")

# Tool for Cal.com user bookings
class CalComGetUserBookingsTool(BaseTool):
    name: str = "calcom_get_user_bookings_tool"
    description: str = "Get user bookings using Cal.com API"
    handle_tool_error: bool = True

    def _run(self, email: str) -> str:
        try:
            result = get_user_bookings(email)
            bookings = json.loads(result).get('user_bookings', [])
            if bookings:
                return f"Found {len(bookings)} bookings for {email}. Booking details: {result}"
            else:
                return f"No bookings found for {email}."
        except Exception as e:
            raise ToolException(f"An error occurred while fetching user bookings: {str(e)}")

# Tool for Cal.com booking cancellation
class CalComCancelBookingTool(BaseTool):
    name: str = "calcom_cancel_booking_tool"
    description: str = "Cancel a booking using Cal.com API"
    handle_tool_error: bool = True

    def _run(self, email: str, date: str, time: str, reason: Optional[str] = None) -> str:
        try:
            result = cancel_user_booking(email, date, time, reason)
            return result
        except Exception as e:
            raise ToolException(f"An error occurred while cancelling the booking: {str(e)}")

# Tool for Cal.com booking rescheduling
class CalComRescheduleBookingTool(BaseTool):
    name: str = "calcom_reschedule_booking_tool"
    description: str = "Reschedule a booking using Cal.com API"
    handle_tool_error: bool = True

    def _run(self, email: str, current_date: str, current_time: str, new_date: Optional[str] = None, new_time: Optional[str] = None, new_duration: Optional[int] = None) -> str:
        try:
            result = reschedule_booking(email, current_date, current_time, new_date, new_time, new_duration)
            return f"Booking rescheduled successfully. Updated booking details: {result}"
        except Exception as e:
            raise ToolException(f"An error occurred while rescheduling the booking: {str(e)}")

# Few-shot examples
few_shot_examples = [
    {"input": "Book a meeting for tomorrow at 2 PM for 30 minutes", "output": "Certainly! I'll schedule that for you. Here's what I'm going to do:\n\nI'll use the calcom_booking_tool with the following parameters:\n- date: [tomorrow's date in YYYY-MM-DD format]\n- time: 14:00\n- duration: 30\n- reason: 'Scheduled meeting'\n- name: [I'll ask for this]\n- email: [I'll ask for this]\n\nFirst, could you please provide your name and email for the booking?"},
    {"input": "Schedule a 2-hour meeting next Monday at 10 AM with John Doe", "output": "Certainly! I'll use the Cal.com booking tool to schedule that meeting for you. Here's what I'm going to do:\n\nI'll use the calcom_booking_tool with the following parameters:\n- date: [next Monday's date in YYYY-MM-DD format]\n- time: 10:00\n- duration: 120\n- reason: 'Meeting with John Doe'\n- name: John Doe\n- email: [I'll ask for this]\n\nCould you please provide your email address for the booking?"},
    {"input": "Book a meeting for yesterday at 3 PM", "output": "I apologize, but I can't book a meeting in the past. The Cal.com booking tool doesn't allow scheduling meetings for dates that have already passed. Would you like to schedule a meeting for a future date instead? If so, please provide a new date and time."},
    {"input": "I'm Sarah. Schedule a 15-minute call with Andre for next Friday at 11:30 AM", "output": "Certainly! I'll use the Cal.com booking tool to schedule that call for you. Here's what I'm going to do:\n\nI'll use the calcom_booking_tool with the following parameters:\n- date: [next Friday's date in YYYY-MM-DD format]\n- time: 11:30\n- duration: 15\n- reason: '15-minute call with Andre'\n- name: Sarah\n- email: [I'll ask for this]\n\nCould you please provide your email address for the booking?"},
    {"input": "I need to book a 45-minute appointment", "output": "Certainly! I can help you book a 45-minute appointment using the Cal.com booking tool. To proceed, I'll need some more information:\n\n1. What date would you like to schedule the appointment for?\n2. What time would you prefer?\n3. What's the reason for the appointment?\n4. What's your name?\n5. What's your email address?\n\nOnce you provide this information, I'll use the calcom_booking_tool to schedule the appointment for you."},
    {"input": "Cancel my meeting scheduled for tomorrow at 2 PM", "output": "Certainly! I'll help you cancel that meeting. To do this, I'll need to use the calcom_cancel_booking_tool. First, could you please provide me with the email address associated with the booking?"},
    {"input": "I need to cancel my appointment on May 15th at 10:30 AM", "output": "Of course, I can help you cancel that appointment. I'll use the calcom_cancel_booking_tool for this. Before I proceed, could you please confirm the email address you used for the booking?"},
    {"input": "Can you cancel all my meetings for next week?", "output": "I apologize, but I can't cancel multiple meetings at once using the calcom_cancel_booking_tool. However, I can help you cancel them one by one. Would you like to start with a specific meeting? If so, please provide the date, time, and your email address for that meeting."},
    {"input": "Reschedule my meeting on May 20th at 2 PM to May 22nd at 3 PM", "output": "Certainly! I'll help you reschedule that meeting. I'll use the calcom_reschedule_booking_tool for this. First, could you please confirm the email address associated with the booking?"},
    {"input": "Change the duration of my appointment on June 5th at 10 AM to 45 minutes", "output": "Of course, I can help you change the duration of your appointment. I'll use the calcom_reschedule_booking_tool for this. Before I proceed, could you please provide the email address you used for the booking?"},
    {"input": "Move my meeting scheduled for tomorrow at 9 AM to 11 AM", "output": "Certainly! I'll help you reschedule your meeting. I'll use the calcom_reschedule_booking_tool for this. First, I need to confirm a few details:\n1. Could you please provide the email address associated with the booking?\n2. To ensure accuracy, could you confirm the exact date of 'tomorrow' in YYYY-MM-DD format?"}
]

# Get today's date
today = date.today().isoformat()

# Chat prompt template
prompt = ChatPromptTemplate.from_messages([
    ("system", f"You are a helpful assistant scheduling bookings with Andre. Today's date is {today}. Follow these guidelines:\n"
    "1. Always ask for email if not provided.\n"
    "2. For booking: Inform user of success or suggest alternatives if failed.\n"
    "3. For getting bookings: Summarize found bookings or offer to schedule if none.\n"
    "4. For cancelling: Confirm details, inform of success or explain failure.\n"
    "5. For rescheduling: Confirm current and new details, can't reschedule to past.\n"
    "6. Use appropriate Cal.com tools for each action."),
    MessagesPlaceholder(variable_name="chat_history"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
    ("human", "{input}")
])

# Initialize the chat model with streaming
model = ChatOpenAI(
    model_name="gpt-4o",
    temperature=0.7,
    streaming=True,
    callbacks=[StreamingStdOutCallbackHandler()]
)

# Set up memory for chat history
memory = ConversationBufferMemory(
    chat_memory=ChatMessageHistory(),
    return_messages=True,
    memory_key="chat_history",
    output_key="output"
)

# Create the agent
tools = [CalComBookingTool(), CalComGetUserBookingsTool(), CalComCancelBookingTool(), CalComRescheduleBookingTool()]
agent = create_openai_functions_agent(model, tools, prompt)

# Set up the agent executor
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    memory=memory,
    verbose=True
)

def response(user_input):
    raw_response = agent_executor.invoke({"input": user_input})
    formatted_output = format_response(raw_response['output'])
    memory.save_context({"input": user_input}, {"output": raw_response['output']})
    return raw_response["output"]

def format_response(text):
    # Convert line breaks to HTML line breaks
    text = text.replace('\n', '<br>')
    
    # Convert markdown-style lists to HTML lists
    text = re.sub(r'(\d+\.) (.+?)(?=<br>\d+\.|<br>$|$)', r'<ol><li>\2</li></ol>', text, flags=re.DOTALL)
    text = re.sub(r'(\* (.+?)(?=<br>\*|<br>$|$))', r'<ul><li>\2</li></ul>', text, flags=re.DOTALL)
    
    # Convert markdown-style headers to HTML headers
    for i in range(6, 0, -1):
        text = re.sub(f'{"#" * i} (.+?)(?=<br>|$)', f'<h{i}>\\1</h{i}>', text)
    
    # Convert markdown-style code blocks to HTML code blocks
    text = re.sub(r'```(\w+)?<br>(.+?)<br>```', r'<pre><code>\2</code></pre>', text, flags=re.DOTALL)
    
    # Convert inline code to HTML inline code
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    
    return text.strip()

# # Main chat loop
# while True:
#     user_input = input("You: ")
#     if user_input.lower() in ["exit", "quit", "bye"]:
#         break
    
#     response = agent_executor.invoke({"input": user_input})
#     print(f"AI: {response['output']}")

# print("Chat ended. Goodbye!")
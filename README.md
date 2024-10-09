# Calendar Chatbot

An intelligent chatbot that manages your calendar events using natural language processing. Seamlessly integrate with Cal.com API to book meetings, list events, and perform various calendar-related tasks.

## Features

- Book new meetings with natural language input
- List scheduled events for a specified time range
- Cancel or reschedule existing events
- Check availability and suggest meeting times
- Set reminders for upcoming events

## Prerequisites

- Python 3.7+
- Cal.com account and API key
- OpenAI API key for natural language processing

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/andrefoo/langchain-calendar-booking-chatbot.git
   cd calendar-chatbot
   ```

2. Create and activate a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

3. Install required packages:
   ```
   pip install -r requirements.txt
   ```

4. Set up environment variables:
   Create a `.env` file in the project root and add your API keys:
   ```
   OPENAI_API_KEY=your_openai_api_key
   CAL_API_KEY=your_cal_api_key
   ```

## Running the Application

Start the chatbot server:

```
python app.py
```

The server will run on a local host.

## Usage

Open the local host in your browser and start chatting with the bot.

The chatbot will process your request and respond with appropriate actions or follow-up questions.

Have fun!
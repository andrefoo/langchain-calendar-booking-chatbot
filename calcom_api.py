import json
import locale
import os
import random
import time
from datetime import datetime, timedelta

import pytz
import requests
from dotenv import load_dotenv
from requests.exceptions import HTTPError, RequestException
from tzlocal import get_localzone
from typing import Optional

load_dotenv()

CAL_API_KEY = os.getenv("CAL_API_KEY")

# Utility functions
def get_system_info():
    timezone = str(get_localzone())
    locale.setlocale(locale.LC_ALL, '')
    language = locale.getlocale()[0].split('_')[0]
    return timezone, language

def find_closest_duration(duration):
    valid_durations = [5, 10, 15, 20, 25, 30, 45, 50, 60, 75, 80, 90, 120, 150, 180, 240, 300, 360, 420, 480]
    return min(valid_durations, key=lambda x: abs(x - duration))

def retry_with_backoff(func):
    def wrapper(*args, **kwargs):
        max_retries = 5
        retry_delay = 1  # Start with a 1-second delay
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except HTTPError as e:
                if e.response.status_code == 429:
                    if attempt == max_retries - 1:
                        raise
                    sleep_time = retry_delay + random.uniform(0, 1)
                    print(f"Rate limited. Retrying in {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise
    return wrapper

@retry_with_backoff
def make_api_request(method, url, **kwargs):
    print("Making API request: ", method, url)
    response = requests.request(method, url, **kwargs)
    response.raise_for_status()
    return response

# Booking creation
def create_booking(date, time, duration, reason, name, email):
    """
    Create a booking using the Cal.com API.
    
    :param date: Date of the meeting (YYYY-MM-DD)
    :param time: Time of the meeting (HH:MM)
    :param duration: Duration of the meeting in minutes
    :param reason: Reason for the meeting
    :param name: Name of the attendee
    :param email: Email of the attendee
    :return: Simplified JSON with booking details if successful, error message otherwise
    """
    timezone, language = get_system_info()

    # Adjust duration to closest valid length
    adjusted_duration = find_closest_duration(duration)

    # Combine date and time into a single datetime object
    try:
        start_time = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
        local_tz = pytz.timezone(timezone)
        start_time = local_tz.localize(start_time)
        end_time = start_time + timedelta(minutes=adjusted_duration)

        # Check if the meeting is in the past
        if start_time < datetime.now(local_tz):
            return json.dumps({"error": "Cannot book a meeting in the past. Please choose a future date and time."})

    except ValueError:
        return json.dumps({"error": "Invalid date or time format. Please use YYYY-MM-DD for date and HH:MM for time."})

    url = "https://api.cal.com/v1/bookings"
    querystring = {"apiKey": CAL_API_KEY}
    
    payload = {
        "start": start_time.isoformat(),
        "end": end_time.isoformat(),
        "eventTypeId": 1202446,
        "responses": {
            "name": name,
            "email": email,
            "notes": reason
        },
        "timeZone": timezone,
        "language": language,
        "metadata": {}
    }

    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, params=querystring)

        if response.status_code == 200:
            booking_data = response.json()
            simplified_response = {
                "Date": start_time.strftime("%B %d, %Y"),
                "Time": f"{start_time.strftime('%I:%M %p')} to {end_time.strftime('%I:%M %p')} ({timezone})",
                "Duration": f"{adjusted_duration} minutes",
                "Reason": reason,
                "Name": name,
                "Email": email,
                "Meeting Link": booking_data.get('metadata', {}).get('videoCallUrl', 'No video call link provided')
            }
            return json.dumps(simplified_response, indent=2)
        else:
            error_message = response.json().get('message', 'Unknown error')
            
            if "Invalid event length" in error_message:
                return json.dumps({"error": f"Error: The requested duration ({duration} minutes) is not valid. The closest valid duration ({adjusted_duration} minutes) will be used instead."})
            elif "Attempting to book a meeting in the past" in error_message:
                return json.dumps({"error": "Error: Cannot book a meeting in the past. Please choose a future date and time."})
            elif "invalid_type" in error_message:
                missing_fields = []
                if not name:
                    missing_fields.append("name")
                if not email:
                    missing_fields.append("email")
                if not date or not time:
                    missing_fields.append("date and time")
                if not reason:
                    missing_fields.append("reason")
                
                if missing_fields:
                    return json.dumps({"error": f"Error: Missing required information. Please provide: {', '.join(missing_fields)}."})
                else:
                    return json.dumps({"error": "Error: Invalid input. Please check all provided information and try again."})
            else:
                return json.dumps({"error": f"Error creating booking: {error_message}"})

    except RequestException as e:
        return json.dumps({"error": f"Error creating booking: {str(e)}"})

# Booking retrieval
def _get_user_bookings_detailed(user_email):
    """
    Private function to retrieve detailed bookings for a specific user from the Cal.com API.
    
    :param user_email: Email address of the user whose bookings are to be retrieved
    :return: List of detailed booking dictionaries or an empty list if an error occurs
    """
    url = "https://api.cal.com/v1/booking-references"
    querystring = {"apiKey": CAL_API_KEY}
    
    try:
        response = make_api_request("GET", url, params=querystring)
        booking_references = response.json().get('booking_references', [])
        
        # Create a set of unique booking IDs
        unique_booking_ids = set(ref['bookingId'] for ref in booking_references if ref['deleted'] is None)
        
        user_bookings = []
        for booking_id in unique_booking_ids:
            booking_url = f"https://api.cal.com/v1/bookings/{booking_id}"
            booking_response = make_api_request("GET", booking_url, params=querystring)
            booking_data = booking_response.json().get('booking', {})
            
            # Check if the booking is not cancelled and belongs to the user
            if (booking_data.get('status') != "CANCELLED" and
                any(attendee['email'] == user_email for attendee in booking_data.get('attendees', []))):
                user_bookings.append(booking_data)
        
        return user_bookings
    except RequestException as e:
        print(f"Error fetching user bookings: {str(e)}")
        return []

def get_user_bookings(user_email):
    """
    Retrieve all bookings for a specific user from the Cal.com API.

    This function fetches all booking references, then retrieves detailed information
    for each booking that belongs to the specified user. It returns a simplified
    version of the booking data, including only the most relevant fields.

    :param user_email: Email address of the user whose bookings are to be retrieved
    :return: JSON string containing an array of user bookings or an error message
    """
    user_bookings = []
    
    try:
        detailed_bookings = _get_user_bookings_detailed(user_email)
        
        for booking_data in detailed_bookings:
            attendees = booking_data.get('attendees', [])
            user_timezone = next((attendee['timeZone'] for attendee in attendees if attendee['email'] == user_email), None)
            
            # Convert startTime and endTime to the user's timezone
            start_time = datetime.fromisoformat(booking_data.get('startTime').replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(booking_data.get('endTime').replace('Z', '+00:00'))
            
            if user_timezone:
                user_tz = pytz.timezone(user_timezone)
                start_time = start_time.astimezone(user_tz)
                end_time = end_time.astimezone(user_tz)
            
            simplified_booking = {
                "startTime": start_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "endTime": end_time.strftime("%Y-%m-%d %H:%M:%S %Z"),
                "description": booking_data.get('description'),
                "timezone": user_timezone,
                "locale": next((attendee['locale'] for attendee in attendees if attendee['email'] == user_email), None),
                "videoCallUrl": booking_data.get('metadata', {}).get('videoCallUrl'),
            }
            user_bookings.append(simplified_booking)
        
        return json.dumps({"user_bookings": user_bookings}, indent=2)

    except RequestException as e:
        return json.dumps({"error": f"Error fetching user bookings: {str(e)}"}, indent=2)

# Booking cancellation
def _find_booking(user_email, meeting_date, meeting_time):
    """
    Find a booking for a user based on the provided date and time.
    
    :param user_email: Email of the user
    :param meeting_date: Date of the meeting (YYYY-MM-DD)
    :param meeting_time: Time of the meeting (HH:MM)
    :return: Matching booking or None if not found
    """
    user_bookings = _get_user_bookings_detailed(user_email)
    
    # Print all startTimes
    print("All booking startTimes:")
    for booking in user_bookings:
        print(booking['startTime'])
    
    # Find the matching booking
    target_datetime = f"{meeting_date}T{meeting_time}:00"
    print("target_datetime: ", target_datetime)
    
    for booking in user_bookings:
        booking_time = datetime.fromisoformat(booking['startTime'].replace('Z', '+00:00'))
        user_timezone = pytz.timezone(booking['attendees'][0]['timeZone'])
        localized_booking_time = booking_time.astimezone(user_timezone)
        print("localized_booking_time: ", localized_booking_time.strftime("%Y-%m-%dT%H:%M:00"))
        
        if localized_booking_time.strftime("%Y-%m-%dT%H:%M:00") == target_datetime:
            return booking
    
    return None

def cancel_user_booking(user_email, meeting_date, meeting_time, cancellation_reason=None):
    """
    Cancel a user's booking based on the provided date and time, and delete the booking reference.
    
    :param user_email: Email of the user
    :param meeting_date: Date of the meeting (YYYY-MM-DD)
    :param meeting_time: Time of the meeting (HH:MM)
    :param cancellation_reason: Optional reason for cancellation
    :return: Success message if cancelled, error message otherwise
    """
    matching_booking = _find_booking(user_email, meeting_date, meeting_time)
    
    print("matching_booking: ", matching_booking)

    if not matching_booking:
        return f"Error: No booking found for {user_email} on {meeting_date} at {meeting_time}"
    
    # Cancel the booking
    booking_id = matching_booking['id']
    cancel_url = f"https://api.cal.com/v1/bookings/{booking_id}/cancel"
    querystring = {"apiKey": CAL_API_KEY}
    
    if cancellation_reason:
        querystring["cancellationReason"] = cancellation_reason
    
    try:
        cancel_response = make_api_request("DELETE", cancel_url, params=querystring)
        
        if cancel_response.status_code == 200:
            # Now delete the booking reference
            booking_references_url = "https://api.cal.com/v1/booking-references"
            references_response = make_api_request("GET", booking_references_url, params={"apiKey": CAL_API_KEY})
            booking_references = references_response.json().get('booking_references', [])
            
            for reference in booking_references:
                if reference['bookingId'] == booking_id:
                    delete_reference_url = f"https://api.cal.com/v1/booking-references/{reference['id']}"
                    delete_response = make_api_request("DELETE", delete_reference_url, params={"apiKey": CAL_API_KEY})
                    
                    if delete_response.status_code == 200:
                        return f"Successfully cancelled booking and deleted reference for {user_email} on {meeting_date} at {meeting_time}"
                    else:
                        return f"Booking cancelled but error deleting reference: {delete_response.json().get('message', 'Unknown error')}"
            
            return f"Successfully cancelled booking for {user_email} on {meeting_date} at {meeting_time}, but no matching reference found to delete"
        else:
            return f"Error cancelling booking: {cancel_response.json().get('message', 'Unknown error')}"
    except RequestException as e:
        return f"Error cancelling booking or deleting reference: {str(e)}"

# Booking reference management
def _remove_cancelled_booking_references():
    """
    Remove all CANCELLED booking references from Cal.com.

    :return: A message indicating the number of cancelled references removed or an error message.
    """
    url = "https://api.cal.com/v1/booking-references"
    querystring = {"apiKey": CAL_API_KEY}

    try:
        # Fetch all booking references
        response = make_api_request("GET", url, params=querystring)
        booking_references = response.json().get('booking_references', [])

        cancelled_refs_removed = 0

        for reference in booking_references:
            booking_id = reference['bookingId']
            reference_id = reference['id']

            # Fetch the booking details
            booking_url = f"https://api.cal.com/v1/bookings/{booking_id}"
            booking_response = make_api_request("GET", booking_url, params=querystring)
            booking_data = booking_response.json().get('booking', {})

            # Check if the booking is cancelled
            if booking_data.get('status') == "CANCELLED":
                # Delete the cancelled booking reference
                delete_url = f"https://api.cal.com/v1/booking-references/{reference_id}"
                delete_response = make_api_request("DELETE", delete_url, params=querystring)

                if delete_response.status_code == 200:
                    cancelled_refs_removed += 1
                else:
                    print(f"Failed to delete reference {reference_id}: {delete_response.json().get('message', 'Unknown error')}")

        return f"Successfully removed {cancelled_refs_removed} cancelled booking references."

    except RequestException as e:
        return f"Error removing cancelled booking references: {str(e)}"

@retry_with_backoff
def reschedule_booking(user_email: str, meeting_date: str, meeting_time: str, new_date: Optional[str] = None, new_time: Optional[str] = None, new_duration: Optional[int] = None) -> dict:
    """
    Reschedule a booking with optional new date, time, and duration.
    
    :param user_email: Email of the user
    :param meeting_date: Current date of the meeting (YYYY-MM-DD)
    :param meeting_time: Current time of the meeting (HH:MM)
    :param new_date: New date for the booking (format: 'YYYY-MM-DD'), optional
    :param new_time: New time for the booking (format: 'HH:MM'), optional
    :param new_duration: New duration for the booking in minutes, optional
    :return: The updated booking information
    """
    # Check if any new values are provided
    if not new_date and not new_time and not new_duration:
        raise ValueError("No new values provided for rescheduling")
    
    matching_booking = _find_booking(user_email, meeting_date, meeting_time)
    
    if not matching_booking:
        raise ValueError(f"No booking found for {user_email} on {meeting_date} at {meeting_time}")

    booking_id = matching_booking['id']
    url = f"https://api.cal.com/v1/bookings/{booking_id}"
    querystring = {"apiKey": CAL_API_KEY}
    headers = {"Content-Type": "application/json"}

    # Get the timezone from the original booking
    timezone = matching_booking['attendees'][0]['timeZone']
    local_tz = pytz.timezone(timezone)

    # Prepare the new start time
    if new_date or new_time:
        new_date = new_date or meeting_date
        new_time = new_time or meeting_time
        start_time = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
        start_time = local_tz.localize(start_time)
    else:
        start_time = datetime.fromisoformat(matching_booking["startTime"].replace('Z', '+00:00'))

    # Calculate the new end time
    if new_duration:
        end_time = start_time + timedelta(minutes=new_duration)
    else:
        original_duration = (datetime.fromisoformat(matching_booking["endTime"].replace('Z', '+00:00')) - 
                             datetime.fromisoformat(matching_booking["startTime"].replace('Z', '+00:00')))
        end_time = start_time + original_duration

    # Check if the new meeting time is in the past
    if start_time < datetime.now(local_tz):
        raise ValueError("Cannot reschedule a meeting to a past date and time. Please choose a future date and time.")

    payload = {
        "startTime": start_time.isoformat(),
        "endTime": end_time.isoformat(),
    }

    # Make the API request to update the booking
    try:
        print("Payload:", json.dumps(payload, indent=2))
        response = requests.patch(url, json=payload, headers=headers, params=querystring)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error rescheduling booking: {str(e)}")
        print(f"Response content: {response.text}")
        raise

# Main execution
# if __name__ == "__main__":
    # Test data
    # user_email = "iluvchoc03@gmail.com"
    # current_date = "2024-10-11"
    # current_time = "09:00"
    
    # print("\nTesting cancel_user_booking:")
    # cancellation_result = cancel_user_booking(user_email, "2024-10-11", "10:00", "Testing cancellation")
    # print(cancellation_result)
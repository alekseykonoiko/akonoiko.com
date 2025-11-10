#!/usr/bin/env python3
"""
Instagram Follower Data Aggregator

Aggregates follower data from Instagram export into a comprehensive JSONL file
with all interactions and engagement metrics for marketing analysis.
"""

import json
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import re
from typing import Dict, List, Optional, Set
import unicodedata

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("Warning: pandas not available. Excel export will be skipped. Install with: pip install pandas openpyxl")

# Base directory for Instagram data (can be overridden)
BASE_DIR = None  # Will be set in process_instagram_data or main


def fix_double_encoded_unicode(text: str) -> str:
    """
    Fix double-encoded Unicode text (mojibake).
    
    Instagram exports sometimes have UTF-8 bytes encoded as Unicode escape sequences.
    When json.load() decodes them, we get characters like U+00D0 (Ð) which are actually
    the first byte of a UTF-8 encoded Cyrillic character.
    
    Example: \u00d0\u00bf in JSON -> "Ð¿" in Python -> should be "п" (Cyrillic 'p')
    """
    if not text:
        return text
    
    try:
        # Check if text contains mojibake patterns
        # Common Cyrillic mojibake uses 0xD0-0xDF and 0x80-0xBF ranges
        has_mojibake_pattern = any(0xD0 <= ord(c) <= 0xDF for c in text) or any(0x80 <= ord(c) <= 0xBF for c in text)
        
        if not has_mojibake_pattern:
            return text
        
        # Count problematic characters (likely mojibake)
        problematic_chars = [c for c in text if 0x80 <= ord(c) <= 0xFF]
        
        # If significant portion is problematic, try to fix
        if len(problematic_chars) > 0:
            # Strategy: treat the entire string as if each character is a byte
            # and try to decode as UTF-8
            # But we need to handle mixed ASCII + mojibake
            
            # Build byte sequence: ASCII chars become their byte value,
            # high chars (0x80-0xFF) also become their byte value
            byte_sequence = bytearray()
            for char in text:
                code = ord(char)
                if code <= 0xFF:
                    byte_sequence.append(code)
                else:
                    # Character outside byte range, encode as UTF-8
                    byte_sequence.extend(char.encode('utf-8'))
            
            # Try to decode as UTF-8
            try:
                fixed = byte_sequence.decode('utf-8')
                # Verify it's actually better - check if it contains Cyrillic
                has_cyrillic = any(0x0400 <= ord(c) <= 0x04FF for c in fixed)
                has_improved_mojibake = not any(0xD0 <= ord(c) <= 0xDF for c in fixed)
                
                # If we got Cyrillic characters or removed mojibake patterns, use it
                if has_cyrillic or (has_improved_mojibake and len(problematic_chars) > len(text) * 0.2):
                    return fixed
            except (UnicodeDecodeError, ValueError):
                # Not valid UTF-8, return original
                pass
        
    except Exception:
        # If anything goes wrong, return original text
        pass
    
    return text


def normalize_username(username: str) -> str:
    """Normalize username for matching (lowercase, remove special chars)."""
    if not username:
        return ""
    # Convert to lowercase and strip whitespace
    username = username.lower().strip()
    # Remove @ symbol if present
    username = username.lstrip('@')
    return username


def extract_username_from_comment(comment_text: str) -> Optional[str]:
    """Extract mentioned username from comment text (e.g., @username)."""
    if not comment_text:
        return None
    # Look for @username pattern
    match = re.search(r'@([a-zA-Z0-9._]+)', comment_text)
    if match:
        return normalize_username(match.group(1))
    return None


def load_followers(base_dir: Path = None) -> Dict[str, Dict]:
    """Load all followers from followers_*.json files."""
    if base_dir is None:
        base_dir = BASE_DIR
    if base_dir is None:
        raise ValueError("Base directory not set. Use process_instagram_data() or set BASE_DIR.")
    
    followers = {}
    followers_dir = base_dir / "connections" / "followers_and_following"
    
    for file_path in followers_dir.glob("followers_*.json"):
        print(f"Loading followers from {file_path.name}...")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for entry in data:
                    if 'string_list_data' in entry and entry['string_list_data']:
                        user_data = entry['string_list_data'][0]
                        username = normalize_username(user_data.get('value', ''))
                        if username:
                            followers[username] = {
                                'username': username,
                                'profile_url': user_data.get('href', ''),
                                'follow_date': user_data.get('timestamp', 0),
                                'follow_date_iso': datetime.fromtimestamp(user_data.get('timestamp', 0)).isoformat() if user_data.get('timestamp') else None,
                            }
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
    
    print(f"Loaded {len(followers)} unique followers")
    return followers


def load_comments(followers: Dict[str, Dict], base_dir: Path = None) -> None:
    """Load and aggregate comment data."""
    if base_dir is None:
        base_dir = BASE_DIR
    if base_dir is None:
        return
    
    comments_file = base_dir / "your_instagram_activity" / "comments" / "post_comments_1.json"
    
    if not comments_file.exists():
        print("Comments file not found")
        return
    
    print("Loading comments...")
    try:
        with open(comments_file, 'r', encoding='utf-8') as f:
            comments_data = json.load(f)
        
        comment_count = 0
        for entry in comments_data:
            if 'string_map_data' not in entry:
                continue
            
            comment_text_raw = entry['string_map_data'].get('Comment', {}).get('value', '')
            # Fix encoding issues
            comment_text = fix_double_encoded_unicode(comment_text_raw)
            timestamp = entry['string_map_data'].get('Time', {}).get('timestamp', 0)
            
            # Try to extract username from comment
            username = extract_username_from_comment(comment_text)
            
            if username and username in followers:
                if 'comments' not in followers[username]:
                    followers[username]['comments'] = {
                        'total_comments': 0,
                        'first_comment_date': None,
                        'last_comment_date': None,
                        'first_comment_timestamp': None,
                        'last_comment_timestamp': None,
                        'sample_comments': []
                    }
                
                followers[username]['comments']['total_comments'] += 1
                
                if timestamp:
                    if (followers[username]['comments']['first_comment_timestamp'] is None or 
                        timestamp < followers[username]['comments']['first_comment_timestamp']):
                        followers[username]['comments']['first_comment_timestamp'] = timestamp
                        followers[username]['comments']['first_comment_date'] = datetime.fromtimestamp(timestamp).isoformat()
                    
                    if (followers[username]['comments']['last_comment_timestamp'] is None or 
                        timestamp > followers[username]['comments']['last_comment_timestamp']):
                        followers[username]['comments']['last_comment_timestamp'] = timestamp
                        followers[username]['comments']['last_comment_date'] = datetime.fromtimestamp(timestamp).isoformat()
                    
                    # Keep up to 5 sample comments
                    if len(followers[username]['comments']['sample_comments']) < 5:
                        followers[username]['comments']['sample_comments'].append({
                            'text': comment_text[:200],  # Truncate long comments
                            'date': datetime.fromtimestamp(timestamp).isoformat()
                        })
                
                comment_count += 1
        
        print(f"Processed {comment_count} comments from followers")
    except Exception as e:
        print(f"Error loading comments: {e}")


def extract_username_from_message_folder(folder_name: str) -> Optional[str]:
    """Extract username from message folder name (format: username_id)."""
    if not folder_name:
        return None
    # Split by underscore and take the first part (before the ID)
    parts = folder_name.split('_')
    if len(parts) > 1:
        # Reconstruct username (everything except the last part which is the ID)
        # Handle cases where username itself has underscores
        # The ID is typically numeric, so we'll try to find where it starts
        username_parts = []
        for part in parts[:-1]:  # All parts except the last
            username_parts.append(part)
        username = '_'.join(username_parts)
        return normalize_username(username)
    return None


def load_messages(followers: Dict[str, Dict], base_dir: Path = None) -> None:
    """Load and aggregate message data from inbox."""
    if base_dir is None:
        base_dir = BASE_DIR
    if base_dir is None:
        return
    
    inbox_dir = base_dir / "your_instagram_activity" / "messages" / "inbox"
    
    if not inbox_dir.exists():
        print("Inbox directory not found")
        return
    
    print("Loading messages...")
    message_folders = list(inbox_dir.iterdir())
    print(f"Found {len(message_folders)} message conversations")
    
    processed = 0
    for folder in message_folders:
        if not folder.is_dir():
            continue
        
        message_file = folder / "message_1.json"
        if not message_file.exists():
            continue
        
        try:
            with open(message_file, 'r', encoding='utf-8') as f:
                message_data = json.load(f)
            
            # Extract participants
            participants = message_data.get('participants', [])
            if not participants:
                continue
            
            # Find the other participant (not the account owner)
            # Account owner is likely "Photia" or similar
            other_participant = None
            for participant in participants:
                name = participant.get('name', '')
                # Skip if it's the account owner
                if 'photia' in name.lower():
                    continue
                other_participant = name
                break
            
            if not other_participant:
                # Try to extract from folder name
                folder_username = extract_username_from_message_folder(folder.name)
                if folder_username:
                    other_participant = folder_username
            
            if not other_participant:
                continue
            
            # Normalize and try to match
            normalized_participant = normalize_username(other_participant)
            
            # Try exact match first
            matched_username = None
            if normalized_participant in followers:
                matched_username = normalized_participant
            else:
                # Try partial matching (username might be in the participant name)
                for username in followers.keys():
                    if username in normalized_participant or normalized_participant in username:
                        matched_username = username
                        break
            
            if not matched_username:
                # Still track messages even if not a follower
                continue
            
            # Process messages
            messages = message_data.get('messages', [])
            if not messages:
                continue
            
            if 'messages' not in followers[matched_username]:
                followers[matched_username]['messages'] = {
                    'has_messaged': True,
                    'message_count': 0,
                    'first_message_date': None,
                    'last_message_date': None,
                    'first_message_timestamp': None,
                    'last_message_timestamp': None,
                    'initiated_conversation': False
                }
            
            # Determine who initiated (first message sender)
            first_message = messages[-1] if messages else None  # Messages are in reverse chronological order
            if first_message:
                first_sender = normalize_username(first_message.get('sender_name', ''))
                followers[matched_username]['messages']['initiated_conversation'] = (
                    first_sender == matched_username or matched_username in first_sender
                )
            
            # Count messages and find dates
            for msg in messages:
                timestamp_ms = msg.get('timestamp_ms', 0)
                if timestamp_ms:
                    timestamp = timestamp_ms / 1000
                    followers[matched_username]['messages']['message_count'] += 1
                    
                    if (followers[matched_username]['messages']['first_message_timestamp'] is None or 
                        timestamp < followers[matched_username]['messages']['first_message_timestamp']):
                        followers[matched_username]['messages']['first_message_timestamp'] = timestamp
                        followers[matched_username]['messages']['first_message_date'] = datetime.fromtimestamp(timestamp).isoformat()
                    
                    if (followers[matched_username]['messages']['last_message_timestamp'] is None or 
                        timestamp > followers[matched_username]['messages']['last_message_timestamp']):
                        followers[matched_username]['messages']['last_message_timestamp'] = timestamp
                        followers[matched_username]['messages']['last_message_date'] = datetime.fromtimestamp(timestamp).isoformat()
            
            processed += 1
            if processed % 100 == 0:
                print(f"Processed {processed} message conversations...")
        
        except Exception as e:
            print(f"Error processing {folder.name}: {e}")
            continue
    
    print(f"Processed {processed} message conversations")


def load_story_interactions(followers: Dict[str, Dict], base_dir: Path = None) -> None:
    """Load story likes and emoji reactions."""
    if base_dir is None:
        base_dir = BASE_DIR
    if base_dir is None:
        return
    
    story_dir = base_dir / "your_instagram_activity" / "story_interactions"
    
    # Load story likes
    story_likes_file = story_dir / "story_likes.json"
    if story_likes_file.exists():
        print("Loading story likes...")
        try:
            with open(story_likes_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            story_activities = data.get('story_activities_story_likes', [])
            for entry in story_activities:
                username = normalize_username(entry.get('title', ''))
                if username and username in followers:
                    if 'story_interactions' not in followers[username]:
                        followers[username]['story_interactions'] = {
                            'story_likes_count': 0,
                            'emoji_reactions_count': 0,
                            'countdown_interactions_count': 0,
                            'last_story_interaction_date': None,
                            'last_story_interaction_timestamp': None
                        }
                    
                    # Count likes (each entry is one like)
                    followers[username]['story_interactions']['story_likes_count'] += 1
                    
                    # Update last interaction date
                    if entry.get('string_list_data') and entry['string_list_data']:
                        timestamp = entry['string_list_data'][0].get('timestamp', 0)
                        if timestamp:
                            if (followers[username]['story_interactions']['last_story_interaction_timestamp'] is None or
                                timestamp > followers[username]['story_interactions']['last_story_interaction_timestamp']):
                                followers[username]['story_interactions']['last_story_interaction_timestamp'] = timestamp
                                followers[username]['story_interactions']['last_story_interaction_date'] = datetime.fromtimestamp(timestamp).isoformat()
        except Exception as e:
            print(f"Error loading story likes: {e}")
    
    # Load emoji reactions
    emoji_reactions_file = story_dir / "emoji_story_reactions.json"
    if emoji_reactions_file.exists():
        print("Loading emoji reactions...")
        try:
            with open(emoji_reactions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            reactions = data.get('story_activities_emoji_quick_reactions', [])
            for entry in reactions:
                username = normalize_username(entry.get('title', ''))
                if username and username in followers:
                    if 'story_interactions' not in followers[username]:
                        followers[username]['story_interactions'] = {
                            'story_likes_count': 0,
                            'emoji_reactions_count': 0,
                            'countdown_interactions_count': 0,
                            'last_story_interaction_date': None,
                            'last_story_interaction_timestamp': None
                        }
                    
                    followers[username]['story_interactions']['emoji_reactions_count'] += 1
                    
                    # Update last interaction date
                    if entry.get('string_list_data') and entry['string_list_data']:
                        timestamp = entry['string_list_data'][0].get('timestamp', 0)
                        if timestamp:
                            if (followers[username]['story_interactions']['last_story_interaction_timestamp'] is None or
                                timestamp > followers[username]['story_interactions']['last_story_interaction_timestamp']):
                                followers[username]['story_interactions']['last_story_interaction_timestamp'] = timestamp
                                followers[username]['story_interactions']['last_story_interaction_date'] = datetime.fromtimestamp(timestamp).isoformat()
        except Exception as e:
            print(f"Error loading emoji reactions: {e}")
    
    # Load countdown interactions
    countdowns_file = story_dir / "countdowns.json"
    if countdowns_file.exists():
        print("Loading countdown interactions...")
        try:
            with open(countdowns_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            countdowns = data.get('story_activities_countdowns', [])
            for entry in countdowns:
                username = normalize_username(entry.get('title', ''))
                if username and username in followers:
                    if 'story_interactions' not in followers[username]:
                        followers[username]['story_interactions'] = {
                            'story_likes_count': 0,
                            'emoji_reactions_count': 0,
                            'countdown_interactions_count': 0,
                            'last_story_interaction_date': None,
                            'last_story_interaction_timestamp': None
                        }
                    
                    followers[username]['story_interactions']['countdown_interactions_count'] += 1
                    
                    # Update last interaction date
                    if entry.get('string_list_data') and entry['string_list_data']:
                        timestamp = entry['string_list_data'][0].get('timestamp', 0)
                        if timestamp:
                            if (followers[username]['story_interactions']['last_story_interaction_timestamp'] is None or
                                timestamp > followers[username]['story_interactions']['last_story_interaction_timestamp']):
                                followers[username]['story_interactions']['last_story_interaction_timestamp'] = timestamp
                                followers[username]['story_interactions']['last_story_interaction_date'] = datetime.fromtimestamp(timestamp).isoformat()
        except Exception as e:
            print(f"Error loading countdown interactions: {e}")


def load_follow_requests(followers: Dict[str, Dict], base_dir: Path = None) -> None:
    """Load pending and recent follow requests."""
    if base_dir is None:
        base_dir = BASE_DIR
    if base_dir is None:
        return
    
    connections_dir = base_dir / "connections" / "followers_and_following"
    
    # Pending follow requests
    pending_file = connections_dir / "pending_follow_requests.json"
    if pending_file.exists():
        try:
            with open(pending_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            requests = data.get('relationships_permanent_follow_requests', [])
            for entry in requests:
                if entry.get('string_list_data') and entry['string_list_data']:
                    username = normalize_username(entry['string_list_data'][0].get('value', ''))
                    if username in followers:
                        followers[username]['status'] = 'pending_request'
        except Exception as e:
            print(f"Error loading pending requests: {e}")
    
    # Recent follow requests
    recent_file = connections_dir / "recent_follow_requests.json"
    if recent_file.exists():
        try:
            with open(recent_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            requests = data.get('relationships_permanent_follow_requests', [])
            for entry in requests:
                if entry.get('string_list_data') and entry['string_list_data']:
                    username = normalize_username(entry['string_list_data'][0].get('value', ''))
                    if username in followers:
                        if 'status' not in followers[username]:
                            followers[username]['status'] = 'recent_request'
        except Exception as e:
            print(f"Error loading recent requests: {e}")


def load_message_requests(followers: Dict[str, Dict], base_dir: Path = None) -> None:
    """Load message requests - these can be from non-followers (valuable leads)."""
    if base_dir is None:
        base_dir = BASE_DIR
    if base_dir is None:
        return
    
    message_requests_dir = base_dir / "your_instagram_activity" / "messages" / "message_requests"
    
    if not message_requests_dir.exists():
        print("Message requests directory not found")
        return
    
    print("Loading message requests...")
    request_folders = list(message_requests_dir.iterdir())
    print(f"Found {len(request_folders)} message request conversations")
    
    processed = 0
    for folder in request_folders:
        if not folder.is_dir():
            continue
        
        message_file = folder / "message_1.json"
        if not message_file.exists():
            continue
        
        try:
            with open(message_file, 'r', encoding='utf-8') as f:
                message_data = json.load(f)
            
            # Extract participants
            participants = message_data.get('participants', [])
            if not participants:
                continue
            
            # Find the other participant (not the account owner)
            other_participant = None
            for participant in participants:
                name = participant.get('name', '')
                # Skip if it's the account owner
                if 'photia' in name.lower():
                    continue
                other_participant = name
                break
            
            if not other_participant:
                # Try to extract from folder name
                folder_username = extract_username_from_message_folder(folder.name)
                if folder_username:
                    other_participant = folder_username
            
            if not other_participant:
                continue
            
            # Normalize and try to match
            normalized_participant = normalize_username(other_participant)
            
            # Check if they're already a follower
            matched_username = None
            if normalized_participant in followers:
                matched_username = normalized_participant
            else:
                # Try partial matching
                for username in followers.keys():
                    if username in normalized_participant or normalized_participant in username:
                        matched_username = username
                        break
            
            # Process messages
            messages = message_data.get('messages', [])
            if not messages:
                continue
            
            # If they're a follower, merge into existing entry
            if matched_username:
                if 'messages' not in followers[matched_username]:
                    followers[matched_username]['messages'] = {
                        'has_messaged': True,
                        'message_count': 0,
                        'first_message_date': None,
                        'last_message_date': None,
                        'first_message_timestamp': None,
                        'last_message_timestamp': None,
                        'initiated_conversation': False,
                        'message_request_count': 0
                    }
                
                # Add message request count
                followers[matched_username]['messages']['message_request_count'] = len(messages)
                followers[matched_username]['messages']['initiated_conversation'] = True  # They initiated (it's a request)
                
                # Update message counts and dates
                for msg in messages:
                    timestamp_ms = msg.get('timestamp_ms', 0)
                    if timestamp_ms:
                        timestamp = timestamp_ms / 1000
                        followers[matched_username]['messages']['message_count'] += 1
                        
                        if (followers[matched_username]['messages']['first_message_timestamp'] is None or 
                            timestamp < followers[matched_username]['messages']['first_message_timestamp']):
                            followers[matched_username]['messages']['first_message_timestamp'] = timestamp
                            followers[matched_username]['messages']['first_message_date'] = datetime.fromtimestamp(timestamp).isoformat()
                        
                        if (followers[matched_username]['messages']['last_message_timestamp'] is None or 
                            timestamp > followers[matched_username]['messages']['last_message_timestamp']):
                            followers[matched_username]['messages']['last_message_timestamp'] = timestamp
                            followers[matched_username]['messages']['last_message_date'] = datetime.fromtimestamp(timestamp).isoformat()
            else:
                # Not a follower - create new entry (valuable lead!)
                # Extract profile URL if possible from folder name or message data
                profile_url = f"https://www.instagram.com/{normalized_participant}"
                
                followers[normalized_participant] = {
                    'username': normalized_participant,
                    'profile_url': profile_url,
                    'follow_date': None,
                    'follow_date_iso': None,
                    'is_follower': False,
                    'messages': {
                        'has_messaged': True,
                        'message_count': len(messages),
                        'message_request_count': len(messages),
                        'first_message_date': None,
                        'last_message_date': None,
                        'first_message_timestamp': None,
                        'last_message_timestamp': None,
                        'initiated_conversation': True
                    },
                    'status': 'message_request_only'
                }
                
                # Set dates
                for msg in messages:
                    timestamp_ms = msg.get('timestamp_ms', 0)
                    if timestamp_ms:
                        timestamp = timestamp_ms / 1000
                        if (followers[normalized_participant]['messages']['first_message_timestamp'] is None or 
                            timestamp < followers[normalized_participant]['messages']['first_message_timestamp']):
                            followers[normalized_participant]['messages']['first_message_timestamp'] = timestamp
                            followers[normalized_participant]['messages']['first_message_date'] = datetime.fromtimestamp(timestamp).isoformat()
                        
                        if (followers[normalized_participant]['messages']['last_message_timestamp'] is None or 
                            timestamp > followers[normalized_participant]['messages']['last_message_timestamp']):
                            followers[normalized_participant]['messages']['last_message_timestamp'] = timestamp
                            followers[normalized_participant]['messages']['last_message_date'] = datetime.fromtimestamp(timestamp).isoformat()
            
            processed += 1
        
        except Exception as e:
            print(f"Error processing message request {folder.name}: {e}")
            continue
    
    print(f"Processed {processed} message request conversations")


def load_recently_unfollowed(followers: Dict[str, Dict], base_dir: Path = None) -> None:
    """Load recently unfollowed profiles."""
    if base_dir is None:
        base_dir = BASE_DIR
    if base_dir is None:
        return
    
    unfollowed_file = base_dir / "connections" / "followers_and_following" / "recently_unfollowed_profiles.json"
    
    if unfollowed_file.exists():
        try:
            with open(unfollowed_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            unfollowed = data.get('relationships_unfollowed_users', [])
            for entry in unfollowed:
                if entry.get('string_list_data') and entry['string_list_data']:
                    username = normalize_username(entry['string_list_data'][0].get('value', ''))
                    if username in followers:
                        followers[username]['status'] = 'recently_unfollowed'
        except Exception as e:
            print(f"Error loading recently unfollowed: {e}")


def calculate_engagement_score(follower_data: Dict) -> float:
    """Calculate engagement score based on interactions."""
    score = 0.0
    
    # Comments (weight: 2 points each)
    if 'comments' in follower_data:
        score += follower_data['comments']['total_comments'] * 2
    
    # Messages (weight: 3 points each)
    if 'messages' in follower_data:
        score += follower_data['messages']['message_count'] * 3
        if follower_data['messages'].get('initiated_conversation'):
            score += 5  # Bonus for initiating
    
    # Story interactions (weight: 1 point each)
    if 'story_interactions' in follower_data:
        score += follower_data['story_interactions']['story_likes_count'] * 1
        score += follower_data['story_interactions']['emoji_reactions_count'] * 1
        score += follower_data['story_interactions'].get('countdown_interactions_count', 0) * 1
    
    # Recency bonus (more recent interactions = higher score)
    now = datetime.now().timestamp()
    if 'comments' in follower_data and follower_data['comments'].get('last_comment_timestamp'):
        days_ago = (now - follower_data['comments']['last_comment_timestamp']) / 86400
        if days_ago < 30:
            score += 10
        elif days_ago < 90:
            score += 5
    
    if 'messages' in follower_data and follower_data['messages'].get('last_message_timestamp'):
        days_ago = (now - follower_data['messages']['last_message_timestamp']) / 86400
        if days_ago < 30:
            score += 10
        elif days_ago < 90:
            score += 5
    
    return round(score, 2)


def infer_discovery_method(follower_data: Dict) -> Optional[str]:
    """Infer how follower might have found the account based on interaction patterns."""
    follow_timestamp = follower_data.get('follow_date', 0)
    
    # If not a follower (message request only), they definitely reached out directly
    if not follower_data.get('is_follower', True):
        return "direct_outreach"
    
    # If no follow date, can't determine
    if not follow_timestamp:
        # Check if they have message requests (indicates they reached out)
        if 'messages' in follower_data and follower_data['messages'].get('initiated_conversation'):
            return "direct_outreach"
        return "unknown"
    
    # Check if they commented before following
    if 'comments' in follower_data and follower_data['comments'].get('first_comment_timestamp'):
        comment_timestamp = follower_data['comments']['first_comment_timestamp']
        if comment_timestamp < follow_timestamp:
            return "content_discovery"  # Found via content before following
    
    # Check if they messaged before following
    if 'messages' in follower_data and follower_data['messages'].get('first_message_timestamp'):
        message_timestamp = follower_data['messages']['first_message_timestamp']
        if message_timestamp < follow_timestamp:
            return "direct_outreach"  # Messaged before following
    
    # Check if they have message requests (indicates they reached out)
    if 'messages' in follower_data and follower_data['messages'].get('initiated_conversation'):
        return "direct_outreach"
    
    # Default assumption
    return "unknown"


def finalize_follower_data(followers: Dict[str, Dict]) -> None:
    """Finalize and enrich follower data with calculated fields."""
    print("Finalizing follower data...")
    
    for username, data in followers.items():
        # Set default status if not set
        if 'status' not in data:
            data['status'] = 'active_follower'
        
        # Calculate engagement score
        data['engagement_score'] = calculate_engagement_score(data)
        
        # Infer discovery method
        data['inferred_discovery_method'] = infer_discovery_method(data)
        
        # Add interaction summary
        has_interactions = (
            'comments' in data or
            'messages' in data or
            'story_interactions' in data
        )
        data['has_interactions'] = has_interactions
        
        # Add total interaction count
        total_interactions = 0
        if 'comments' in data:
            total_interactions += data['comments']['total_comments']
        if 'messages' in data:
            total_interactions += data['messages']['message_count']
        if 'story_interactions' in data:
            total_interactions += data['story_interactions']['story_likes_count']
            total_interactions += data['story_interactions']['emoji_reactions_count']
            total_interactions += data['story_interactions'].get('countdown_interactions_count', 0)
        data['total_interactions'] = total_interactions
        
        # Set is_follower flag (default True for existing followers)
        if 'is_follower' not in data:
            data['is_follower'] = True


def export_to_jsonl(followers: Dict[str, Dict], output_file: Path) -> None:
    """Export followers data to JSONL format."""
    print(f"Exporting to {output_file}...")
    
    # Sort by engagement score (descending)
    sorted_followers = sorted(
        followers.items(),
        key=lambda x: x[1].get('engagement_score', 0),
        reverse=True
    )
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for username, data in sorted_followers:
            # Clean up None values and convert to JSON-serializable format
            cleaned_data = {}
            for key, value in data.items():
                if value is None:
                    continue
                if isinstance(value, dict):
                    # Remove None values from nested dicts
                    cleaned_value = {k: v for k, v in value.items() if v is not None}
                    if cleaned_value:
                        cleaned_data[key] = cleaned_value
                else:
                    cleaned_data[key] = value
            
            f.write(json.dumps(cleaned_data, ensure_ascii=False) + '\n')
    
    print(f"Exported {len(sorted_followers)} followers to {output_file}")


def flatten_follower_data(follower_data: Dict) -> Dict:
    """Flatten nested follower data structure for Excel export."""
    flat = {}
    
    # Basic fields
    flat['username'] = follower_data.get('username', '')
    flat['profile_url'] = follower_data.get('profile_url', '')
    flat['follow_date'] = follower_data.get('follow_date_iso', '')
    flat['is_follower'] = follower_data.get('is_follower', True)
    flat['status'] = follower_data.get('status', '')
    flat['engagement_score'] = follower_data.get('engagement_score', 0)
    flat['inferred_discovery_method'] = follower_data.get('inferred_discovery_method', '')
    flat['has_interactions'] = follower_data.get('has_interactions', False)
    flat['total_interactions'] = follower_data.get('total_interactions', 0)
    
    # Comments
    if 'comments' in follower_data:
        comments = follower_data['comments']
        flat['total_comments'] = comments.get('total_comments', 0)
        flat['first_comment_date'] = comments.get('first_comment_date', '')
        flat['last_comment_date'] = comments.get('last_comment_date', '')
        # Sample comments as text
        sample = comments.get('sample_comments', [])
        flat['sample_comments'] = ' | '.join([c.get('text', '')[:50] for c in sample[:3]])
    else:
        flat['total_comments'] = 0
        flat['first_comment_date'] = ''
        flat['last_comment_date'] = ''
        flat['sample_comments'] = ''
    
    # Messages
    if 'messages' in follower_data:
        messages = follower_data['messages']
        flat['has_messaged'] = messages.get('has_messaged', False)
        flat['message_count'] = messages.get('message_count', 0)
        flat['message_request_count'] = messages.get('message_request_count', 0)
        flat['first_message_date'] = messages.get('first_message_date', '')
        flat['last_message_date'] = messages.get('last_message_date', '')
        flat['initiated_conversation'] = messages.get('initiated_conversation', False)
    else:
        flat['has_messaged'] = False
        flat['message_count'] = 0
        flat['message_request_count'] = 0
        flat['first_message_date'] = ''
        flat['last_message_date'] = ''
        flat['initiated_conversation'] = False
    
    # Story interactions
    if 'story_interactions' in follower_data:
        story = follower_data['story_interactions']
        flat['story_likes_count'] = story.get('story_likes_count', 0)
        flat['emoji_reactions_count'] = story.get('emoji_reactions_count', 0)
        flat['countdown_interactions_count'] = story.get('countdown_interactions_count', 0)
        flat['last_story_interaction_date'] = story.get('last_story_interaction_date', '')
    else:
        flat['story_likes_count'] = 0
        flat['emoji_reactions_count'] = 0
        flat['countdown_interactions_count'] = 0
        flat['last_story_interaction_date'] = ''
    
    return flat


def export_to_excel(followers: Dict[str, Dict], output_file: Path) -> None:
    """Export followers data to Excel with Russian localization."""
    if not PANDAS_AVAILABLE:
        print("Skipping Excel export - pandas not available")
        return
    
    print(f"Exporting to Excel: {output_file}...")
    
    # Flatten all follower data
    flattened_data = []
    for username, data in followers.items():
        flattened_data.append(flatten_follower_data(data))
    
    # Create DataFrame
    df = pd.DataFrame(flattened_data)
    
    # Russian column names mapping
    russian_columns = {
        'username': 'Имя пользователя',
        'profile_url': 'Ссылка на профиль',
        'follow_date': 'Дата подписки',
        'is_follower': 'Является подписчиком',
        'status': 'Статус',
        'engagement_score': 'Оценка вовлеченности',
        'inferred_discovery_method': 'Способ обнаружения',
        'has_interactions': 'Есть взаимодействия',
        'total_interactions': 'Всего взаимодействий',
        'total_comments': 'Всего комментариев',
        'first_comment_date': 'Дата первого комментария',
        'last_comment_date': 'Дата последнего комментария',
        'sample_comments': 'Примеры комментариев',
        'has_messaged': 'Отправлял сообщения',
        'message_count': 'Количество сообщений',
        'message_request_count': 'Количество запросов на сообщение',
        'first_message_date': 'Дата первого сообщения',
        'last_message_date': 'Дата последнего сообщения',
        'initiated_conversation': 'Инициировал разговор',
        'story_likes_count': 'Лайки историй',
        'emoji_reactions_count': 'Эмодзи реакции на истории',
        'countdown_interactions_count': 'Взаимодействия с таймерами',
        'last_story_interaction_date': 'Дата последнего взаимодействия с историей'
    }
    
    # Rename columns
    df = df.rename(columns=russian_columns)
    
    # Create Excel writer
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Write data sheet
        df.to_excel(writer, sheet_name='Данные', index=False)
        
        # Create explanations sheet
        explanations = [
            ['Поле', 'Описание'],
            ['Имя пользователя', 'Имя пользователя в Instagram (без @)'],
            ['Ссылка на профиль', 'Полная ссылка на профиль пользователя'],
            ['Дата подписки', 'Дата и время, когда пользователь подписался на ваш аккаунт'],
            ['Является подписчиком', 'Да/Нет - является ли пользователь подписчиком (Нет для запросов на сообщение)'],
            ['Статус', 'Статус пользователя: активный подписчик, ожидающий запрос, недавно отписался, только запрос на сообщение'],
            ['Оценка вовлеченности', 'Рассчитанная оценка вовлеченности пользователя (см. формулу ниже)'],
            ['Способ обнаружения', 'Как пользователь мог найти ваш аккаунт: через контент, прямой контакт, неизвестно'],
            ['Есть взаимодействия', 'Да/Нет - есть ли у пользователя какие-либо взаимодействия'],
            ['Всего взаимодействий', 'Общее количество всех взаимодействий (комментарии + сообщения + истории)'],
            ['Всего комментариев', 'Общее количество комментариев, оставленных пользователем'],
            ['Дата первого комментария', 'Дата и время первого комментария от пользователя'],
            ['Дата последнего комментария', 'Дата и время последнего комментария от пользователя'],
            ['Примеры комментариев', 'Примеры комментариев пользователя (первые 3)'],
            ['Отправлял сообщения', 'Да/Нет - отправлял ли пользователь сообщения'],
            ['Количество сообщений', 'Общее количество сообщений в переписке'],
            ['Количество запросов на сообщение', 'Количество сообщений в запросах (для не подписчиков)'],
            ['Дата первого сообщения', 'Дата и время первого сообщения от пользователя'],
            ['Дата последнего сообщения', 'Дата и время последнего сообщения от пользователя'],
            ['Инициировал разговор', 'Да/Нет - начал ли пользователь разговор первым'],
            ['Лайки историй', 'Количество лайков, поставленных на ваши истории'],
            ['Эмодзи реакции на истории', 'Количество эмодзи реакций на ваши истории'],
            ['Взаимодействия с таймерами', 'Количество взаимодействий с таймерами обратного отсчета в историях'],
            ['Дата последнего взаимодействия с историей', 'Дата последнего взаимодействия с любой историей'],
            ['', ''],
            ['ФОРМУЛА ОЦЕНКИ ВОВЛЕЧЕННОСТИ', ''],
            ['Компонент', 'Баллы'],
            ['Комментарий', '2 балла за каждый комментарий'],
            ['Сообщение', '3 балла за каждое сообщение'],
            ['Бонус за инициацию разговора', '5 дополнительных баллов, если пользователь начал разговор'],
            ['Лайк истории', '1 балл за каждый лайк истории'],
            ['Эмодзи реакция на историю', '1 балл за каждую эмодзи реакцию'],
            ['Взаимодействие с таймером', '1 балл за каждое взаимодействие с таймером'],
            ['Бонус за актуальность (взаимодействие <30 дней)', '10 дополнительных баллов'],
            ['Бонус за актуальность (взаимодействие <90 дней)', '5 дополнительных баллов'],
            ['', ''],
            ['СТАТУСЫ ПОЛЬЗОВАТЕЛЕЙ', ''],
            ['Статус', 'Описание'],
            ['active_follower', 'Активный подписчик'],
            ['pending_request', 'Ожидающий запрос на подписку'],
            ['recent_request', 'Недавний запрос на подписку'],
            ['recently_unfollowed', 'Недавно отписался'],
            ['message_request_only', 'Только запрос на сообщение (не подписчик)'],
            ['', ''],
            ['СПОСОБЫ ОБНАРУЖЕНИЯ', ''],
            ['Способ', 'Описание'],
            ['content_discovery', 'Нашел через контент (прокомментировал до подписки)'],
            ['direct_outreach', 'Прямой контакт (написал сообщение до подписки или инициировал разговор)'],
            ['unknown', 'Неизвестно (нет четкого паттерна)'],
        ]
        
        df_explanations = pd.DataFrame(explanations[1:], columns=explanations[0])
        df_explanations.to_excel(writer, sheet_name='Описание полей', index=False)
        
        # Auto-adjust column widths
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width
    
    print(f"Exported {len(flattened_data)} entries to {output_file}")


def process_instagram_data(
    data_directory: Path,
    output_directory: Path,
    output_filename: str = "followers_aggregated",
    export_jsonl: bool = True,
    export_excel: bool = True,
    progress_callback: callable = None
) -> Dict:
    """
    Main processing function that can be called from GUI.
    
    Args:
        data_directory: Path to directory containing Instagram data (should contain instagram-photia folder)
        output_directory: Directory where output files will be saved
        output_filename: Base name for output files (without extension)
        export_jsonl: Whether to export JSONL file
        export_excel: Whether to export Excel file
        progress_callback: Optional callback function(status_message, progress_percent)
    
    Returns:
        Dictionary with processing results and statistics
    """
    # Find instagram-photia folder
    instagram_folder = data_directory / "instagram-photia"
    if not instagram_folder.exists():
        # Try if data_directory itself is the instagram-photia folder
        if (data_directory / "connections").exists():
            instagram_folder = data_directory
        else:
            raise ValueError(f"Instagram data folder not found in {data_directory}")
    
    base_dir = instagram_folder
    
    if progress_callback:
        progress_callback("Загрузка подписчиков...", 5)
    
    # Load all followers
    followers = load_followers(base_dir)
    
    if progress_callback:
        progress_callback(f"Загружено {len(followers)} подписчиков. Обработка комментариев...", 15)
    
    # Load and aggregate interaction data
    load_comments(followers, base_dir)
    
    if progress_callback:
        progress_callback("Обработка сообщений...", 30)
    
    load_messages(followers, base_dir)
    
    if progress_callback:
        progress_callback("Обработка взаимодействий с историями...", 50)
    
    load_story_interactions(followers, base_dir)
    
    if progress_callback:
        progress_callback("Обработка запросов на сообщения...", 65)
    
    load_message_requests(followers, base_dir)
    load_follow_requests(followers, base_dir)
    load_recently_unfollowed(followers, base_dir)
    
    if progress_callback:
        progress_callback("Финализация данных...", 80)
    
    # Finalize data
    finalize_follower_data(followers)
    
    results = {
        'total_entries': len(followers),
        'followers_count': sum(1 for f in followers.values() if f.get('is_follower', True)),
        'non_followers_count': sum(1 for f in followers.values() if not f.get('is_follower', True)),
        'entries_with_interactions': sum(1 for f in followers.values() if f.get('has_interactions')),
        'output_files': []
    }
    
    # Export to JSONL
    if export_jsonl:
        if progress_callback:
            progress_callback("Экспорт в JSONL...", 85)
        output_file = output_directory / f"{output_filename}.jsonl"
        export_to_jsonl(followers, output_file)
        results['output_files'].append(str(output_file))
    
    # Export to Excel
    if export_excel:
        if progress_callback:
            progress_callback("Экспорт в Excel...", 90)
        excel_file = output_directory / f"{output_filename}.xlsx"
        export_to_excel(followers, excel_file)
        results['output_files'].append(str(excel_file))
    
    if progress_callback:
        progress_callback("Готово!", 100)
    
    return results


def main():
    """Main execution function for command line usage."""
    # Set default BASE_DIR for command line usage
    global BASE_DIR
    BASE_DIR = Path(__file__).parent / "instagram-photia"
    
    print("Instagram Follower Data Aggregator")
    print("=" * 50)
    
    # Load all followers
    followers = load_followers()
    
    # Load and aggregate interaction data
    load_comments(followers)
    load_messages(followers)
    load_story_interactions(followers)
    load_message_requests(followers)
    load_follow_requests(followers)
    load_recently_unfollowed(followers)
    
    # Finalize data
    finalize_follower_data(followers)
    
    # Export to JSONL
    output_file = Path(__file__).parent / "followers_aggregated.jsonl"
    export_to_jsonl(followers, output_file)
    
    # Export to Excel
    excel_file = Path(__file__).parent / "followers_aggregated.xlsx"
    export_to_excel(followers, excel_file)
    
    # Print summary
    print("\n" + "=" * 50)
    print("Summary:")
    print(f"Total entries: {len(followers)}")
    followers_count = sum(1 for f in followers.values() if f.get('is_follower', True))
    non_followers_count = len(followers) - followers_count
    print(f"Followers: {followers_count}")
    print(f"Non-followers (message requests): {non_followers_count}")
    followers_with_interactions = sum(1 for f in followers.values() if f.get('has_interactions'))
    print(f"Entries with interactions: {followers_with_interactions}")
    print(f"JSONL output: {output_file}")
    print(f"Excel output: {excel_file}")


if __name__ == "__main__":
    main()


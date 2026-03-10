# bot.py
# Rihu - Telegram AI Bot
# Developer: RIYAD (@RIYAD_CODER)

import logging
import json
import requests
import re
import urllib.parse
import sqlite3
import os
from typing import Dict, Optional
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8541637094:AAF_EQpuQkWviYMV-myRZvl3D8KqzLkkplk"
ADMIN_ID = 8124942237  # Replace with actual admin Telegram ID
TEXT_API_URL = "https://riyad-coder-gemini-api.onrender.com/api/ask?prompt="
IMAGE_API_URL = "ENTER_YOUR_IMG_API"
# =======================================================

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Database setup for chat history
DB_PATH = "chat_history.db"

def init_db():
    """Initialize SQLite database for chat history."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            chat_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_chat_history(chat_id: int, limit: int = 20) -> list:
    """Get chat history for a specific chat from database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT role, content FROM chat_history WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
        (chat_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    # Return in chronological order
    return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

def add_to_history(chat_id: int, role: str, content: str):
    """Add message to chat history in database."""
    # Clean content for storage
    clean_content = re.sub(r'```[\w]*\n?', '', content).replace('```', '')
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO chat_history (chat_id, role, content) VALUES (?, ?, ?)",
        (chat_id, role, clean_content)
    )
    conn.commit()
    conn.close()

# Store last bot message IDs for reply detection
last_bot_messages: Dict[int, int] = {}

# Store original messages for edit detection (in memory for quick access)
original_messages: Dict[int, Dict] = {}

# Initialize database
init_db()


def detect_language(code: str) -> str:
    """Detect programming language from code."""
    code = code.strip()
    
    python_patterns = [
        r'def\s+\w+\s*\([^)]*\)\s*:',
        r'class\s+\w+[^:]*:',
        r'import\s+\w+',
        r'from\s+\w+\s+import',
        r'print\s*\(',
        r'if\s+__name__\s*==\s*["\']__main__["\']',
        r'elif\s+',
        r'except\s+',
        r'raise\s+',
        r'@\w+',
        r'lambda\s+',
        r'yield\s+',
        r'async\s+def',
        r'await\s+',
    ]
    
    js_patterns = [
        r'const\s+\w+\s*=',
        r'let\s+\w+\s*=',
        r'var\s+\w+\s*=',
        r'function\s+\w+\s*\(',
        r'=>',
        r'console\.log',
        r'document\.',
        r'window\.',
        r'export\s+default',
        r'import\s+.*\s+from',
        r'require\s*\(',
    ]
    
    java_patterns = [
        r'public\s+class',
        r'public\s+static\s+void',
        r'System\.out\.println',
        r'private\s+\w+',
        r'protected\s+\w+',
        r'extends\s+\w+',
        r'implements\s+\w+',
    ]
    
    cpp_patterns = [
        r'#include\s*<[^>]+>',
        r'int\s+main\s*\(',
        r'std::',
        r'cout\s*<<',
        r'printf\s*\(',
        r'struct\s+\w+',
    ]
    
    html_patterns = [
        r'<html',
        r'<div',
        r'<body',
        r'<head',
        r'<script',
        r'<style',
        r'<!DOCTYPE',
    ]
    
    css_patterns = [
        r'\.\w+\s*\{',
        r'#\w+\s*\{',
        r'@\w+',
        r'margin\s*:',
        r'padding\s*:',
        r'display\s*:',
    ]
    
    bash_patterns = [
        r'#!/bin/bash',
        r'#!/bin/sh',
        r'echo\s+',
        r'\$\w+',
        r'\|\s*grep',
        r'apt\s+',
        r'sudo\s+',
    ]
    
    sql_patterns = [
        r'SELECT\s+',
        r'FROM\s+\w+',
        r'WHERE\s+',
        r'INSERT\s+INTO',
        r'UPDATE\s+\w+',
        r'DELETE\s+FROM',
        r'CREATE\s+TABLE',
    ]
    
    scores = {
        'python': sum(1 for p in python_patterns if re.search(p, code, re.IGNORECASE)),
        'javascript': sum(1 for p in js_patterns if re.search(p, code, re.IGNORECASE)),
        'java': sum(1 for p in java_patterns if re.search(p, code, re.IGNORECASE)),
        'cpp': sum(1 for p in cpp_patterns if re.search(p, code, re.IGNORECASE)),
        'html': sum(1 for p in html_patterns if re.search(p, code, re.IGNORECASE)),
        'css': sum(1 for p in css_patterns if re.search(p, code, re.IGNORECASE)),
        'bash': sum(1 for p in bash_patterns if re.search(p, code, re.IGNORECASE)),
        'sql': sum(1 for p in sql_patterns if re.search(p, code, re.IGNORECASE)),
    }
    
    max_score = max(scores.values())
    if max_score > 0:
        return max(scores, key=scores.get)
    return ''


def is_code_block(text: str) -> bool:
    """Check if text contains code patterns."""
    code_indicators = [
        r'^\s*def\s+\w+\s*\(',
        r'^\s*class\s+\w+',
        r'^\s*import\s+\w+',
        r'^\s*from\s+\w+\s+import',
        r'print\s*\(',
        r'if\s+__name__\s*==',
        r'^\s*#\s*include',
        r'^\s*int\s+main\s*\(',
        r'function\s+\w+\s*\(',
        r'const\s+\w+\s*=',
        r'let\s+\w+\s*=',
        r'var\s+\w+\s*=',
        r'console\.log',
        r'<\w+>',
        r'<\w+\s',
        r'{\s*$',
        r'^\s*}\s*$',
        r'for\s*\(',
        r'while\s*\(',
        r'if\s*\(',
        r'return\s+',
        r'@\w+',
    ]
    
    lines = text.split('\n')
    code_line_count = 0
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        for pattern in code_indicators:
            if re.search(pattern, stripped, re.IGNORECASE):
                code_line_count += 1
                break
    
    return code_line_count >= 2


def format_code_blocks(text: str) -> str:
    """Format code blocks properly with markdown."""
    if text.strip().startswith('```') and text.strip().endswith('```'):
        return text
    
    if is_code_block(text):
        language = detect_language(text)
        if language:
            return f"```{language}\n{text}\n```"
        else:
            return f"```\n{text}\n```"
    
    lines = text.split('\n')
    in_code_block = False
    code_buffer = []
    result = []
    current_language = ''
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        if not in_code_block and (stripped.startswith('def ') or 
                                   stripped.startswith('class ') or 
                                   stripped.startswith('import ') or
                                   stripped.startswith('function ') or
                                   stripped.startswith('const ') or
                                   stripped.startswith('let ') or
                                   stripped.startswith('var ') or
                                   stripped.startswith('#include') or
                                   stripped.startswith('public class') or
                                   stripped.startswith('<?php') or
                                   stripped.startswith('<html') or
                                   stripped.startswith('SELECT ') or
                                   stripped.startswith('CREATE TABLE') or
                                   stripped.startswith('if __name__')):
            if code_buffer and not all(not l.strip() for l in code_buffer):
                result.append('\n'.join(code_buffer))
                code_buffer = []
            in_code_block = True
            # Look ahead to detect language
            look_ahead = '\n'.join(lines[i:min(i+5, len(lines))])
            current_language = detect_language(look_ahead)
        
        if in_code_block:
            if not stripped and code_buffer:
                next_idx = i + 1
                if next_idx < len(lines):
                    next_line = lines[next_idx].strip()
                    if next_line and not is_code_line(next_line):
                        lang_tag = current_language if current_language else ''
                        result.append(f"```{lang_tag}\n" + '\n'.join(code_buffer) + "\n```")
                        code_buffer = []
                        in_code_block = False
                        current_language = ''
                        result.append(line)
                        continue
            
            code_buffer.append(line)
        else:
            result.append(line)
    
    if in_code_block and code_buffer:
        lang_tag = current_language if current_language else ''
        result.append(f"```{lang_tag}\n" + '\n'.join(code_buffer) + "\n```")
    elif code_buffer:
        result.append('\n'.join(code_buffer))
    
    return '\n'.join(result)


def is_code_line(line: str) -> bool:
    """Check if a single line looks like code."""
    patterns = [
        r'^\s*def\s+\w',
        r'^\s*class\s+\w',
        r'^\s*import\s+\w',
        r'^\s*from\s+\w',
        r'print\s*\(',
        r'^\s*#\s*include',
        r'^\s*int\s+main',
        r'function\s+\w',
        r'const\s+\w',
        r'let\s+\w',
        r'var\s+\w',
        r'console\.log',
        r'^\s*}\s*$',
        r'^\s*{\s*$',
        r'^\s*return\s+',
        r'^\s*if\s*\(',
        r'^\s*for\s*\(',
        r'^\s*while\s*\(',
        r'@\w+',
        r'^\s*\w+\s*\([^)]*\)\s*{?\s*$',
    ]
    return any(re.search(p, line, re.IGNORECASE) for p in patterns)


def extract_image_prompt(text: str) -> Optional[str]:
    """Extract image generation prompt from AI response JSON."""
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict):
            if data.get("action") == "image_generation":
                return data.get("action_input") or data.get("prompt") or data.get("description")
    except json.JSONDecodeError:
        pass
    
    json_pattern = r'\{\s*"action"\s*:\s*"image_generation"\s*,\s*"action_input"\s*:\s*"([^"]+)"\s*\}'
    match = re.search(json_pattern, text)
    if match:
        return match.group(1)
    
    alt_patterns = [
        r'"action"\s*:\s*"image_generation".*?"action_input"\s*:\s*"([^"]+)"',
        r'"action"\s*:\s*"generate_image".*?"prompt"\s*:\s*"([^"]+)"',
    ]
    for pattern in alt_patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            return match.group(1)
    
    return None


async def generate_image(prompt: str) -> Optional[str]:
    """Generate image using free API."""
    try:
        encoded_prompt = requests.utils.quote(prompt)
        image_url = f"{IMAGE_API_URL}{encoded_prompt}?width=1024&height=1024&nologo=true"
        
        # Verify image URL is accessible (60 seconds timeout)
        response = requests.get(image_url, timeout=60, stream=True)
        if response.status_code == 200:
            return image_url
        else:
            logger.error(f"Image API returned status {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        logger.error("Image generation timed out")
        return None
    except Exception as e:
        logger.error(f"Image generation error: {e}")
        return None


async def get_ai_response(chat_id: int, message: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get AI response from text API using GET method."""
    try:
        # Add user message to history
        add_to_history(chat_id, "user", message)
        
        # Get full chat history
        history = get_chat_history(chat_id, limit=20)
        
        # Build prompt with history context
        history_context = ""
        for msg in history[:-1]:  # Exclude the last message (current one)
            prefix = "User: " if msg["role"] == "user" else "Assistant: "
            history_context += f"{prefix}{msg['content']}\n"
        
        # Combine history with current message
        if history_context:
            full_prompt = f"Previous conversation:\n{history_context}\n\nCurrent question: {message}"
        else:
            full_prompt = message
        
        encoded_prompt = urllib.parse.quote(full_prompt)
        full_url = f"{TEXT_API_URL}{encoded_prompt}"
        
        # 30 seconds timeout for text API
        response = requests.get(full_url, timeout=30)
        
        if response.status_code == 200:
            try:
                data = response.json()
                ai_response = data.get("response") or data.get("message") or data.get("text") or data.get("answer") or data.get("result")
                
                if not ai_response:
                    if isinstance(data, str):
                        ai_response = data
                    else:
                        ai_response = str(data)
                
                # Check if response contains image generation JSON
                image_prompt = extract_image_prompt(ai_response)
                if image_prompt:
                    # Send waiting message
                    waiting_msg = await update.message.reply_text("Creating your picture please wait..")
                    
                    # Generate image
                    image_url = await generate_image(image_prompt)
                    
                    # Delete waiting message
                    try:
                        await waiting_msg.delete()
                    except:
                        pass
                    
                    if image_url:
                        try:
                            await update.message.reply_photo(photo=image_url)
                            # Store in history
                            add_to_history(chat_id, "assistant", f"[Generated image: {image_prompt}]")
                        except Exception as e:
                            logger.error(f"Error sending image: {e}")
                            await update.message.reply_text("Image generation failed. Please try again later.")
                    else:
                        await update.message.reply_text("Image generation failed. Please try again later.")
                    return None
                
                # Format code blocks
                ai_response = format_code_blocks(ai_response)
                
                # Add to history
                add_to_history(chat_id, "assistant", ai_response)
                
                return ai_response
                
            except Exception as e:
                logger.error(f"JSON parsing error: {e}")
                ai_response = response.text
                
                # Check for image generation in plain text
                image_prompt = extract_image_prompt(ai_response)
                if image_prompt:
                    waiting_msg = await update.message.reply_text("Creating your picture please wait..")
                    image_url = await generate_image(image_prompt)
                    try:
                        await waiting_msg.delete()
                    except:
                        pass
                    
                    if image_url:
                        await update.message.reply_photo(photo=image_url)
                        add_to_history(chat_id, "assistant", f"[Generated image: {image_prompt}]")
                    else:
                        await update.message.reply_text("Image generation failed. Please try again later.")
                    return None
                
                ai_response = format_code_blocks(ai_response)
                add_to_history(chat_id, "assistant", ai_response)
                return ai_response
        else:
            logger.error(f"API Error: {response.status_code} - {response.text}")
            return "AI server error. Please try again later."
            
    except requests.exceptions.Timeout:
        logger.error("API request timed out")
        return "AI server error. Please try again later."
    except requests.exceptions.ConnectionError:
        logger.error("API connection error")
        return "AI server error. Please try again later."
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {e}")
        return "AI server error. Please try again later."
    except Exception as e:
        logger.error(f"AI Response Error: {e}")
        return "AI server error. Please try again later."


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome_text = (
        "I am AI BOT, a powerful AI bot created by SAMI 🤖\n"
        "Ask me anything and I will answer your questions."
    )
    await update.message.reply_text(welcome_text)


async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin command - only for admin."""
    user_id = update.effective_user.id
    
    if user_id == ADMIN_ID:
        await update.message.reply_text("Boss, I am a powerful AI and group helper created by you 💪")
    else:
        await update.message.reply_text("This command is for admin only.")


async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ai command in groups."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    message_text = update.message.text
    if message_text.startswith('/ai'):
        question = message_text[3:].strip()
    else:
        question = message_text.strip()
    
    if not question:
        await update.message.reply_text("Please enter your question. Example: /ai What is the capital of Bangladesh?")
        return
    
    # Check for admin special trigger "who made you"
    if user_id == ADMIN_ID and question.lower() == "who made you":
        await update.message.reply_text("Boss, I am a powerful AI and group helper created by you 💪")
        return
    
    # Check for direct image generation request from user
    lower_question = question.lower()
    if "pik generate" in lower_question or "image generate" in lower_question:
        # Extract prompt
        prompt = ""
        if "pik generate" in lower_question:
            prompt = question.lower().split("pik generate", 1)[1].strip()
        elif "image generate" in lower_question:
            prompt = question.lower().split("image generate", 1)[1].strip()
        
        if prompt:
            waiting_msg = await update.message.reply_text("Creating your picture please wait..")
            image_url = await generate_image(prompt)
            try:
                await waiting_msg.delete()
            except:
                pass
            
            if image_url:
                try:
                    await update.message.reply_photo(photo=image_url)
                    add_to_history(chat_id, "user", question)
                    add_to_history(chat_id, "assistant", f"[Generated image: {prompt}]")
                except Exception as e:
                    logger.error(f"Error sending image: {e}")
                    await update.message.reply_text("Image generation failed. Please try again later.")
            else:
                await update.message.reply_text("Image generation failed. Please try again later.")
            return
    
    # Get AI response (handles image generation internally)
    response = await get_ai_response(chat_id, question, update, context)
    
    if response:
        try:
            sent_msg = await update.message.reply_text(response, parse_mode='Markdown')
            last_bot_messages[chat_id] = sent_msg.message_id
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            try:
                sent_msg = await update.message.reply_text(response)
                last_bot_messages[chat_id] = sent_msg.message_id
            except:
                pass


async def private_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle private chat messages."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    message_text = update.message.text
    
    # Check for admin special triggers
    if user_id == ADMIN_ID:
        if message_text.strip().lower() == "/admin":
            await update.message.reply_text("Boss, I am a powerful AI and group helper created by you 💪")
            return
        if message_text.strip().lower() == "who made you":
            await update.message.reply_text("Boss, I am a powerful AI and group helper created by you 💪")
            return
    
    # Check for direct image generation request
    lower_text = message_text.lower()
    if "pik generate" in lower_text or "image generate" in lower_text:
        prompt = ""
        if "pik generate" in lower_text:
            prompt = message_text.lower().split("pik generate", 1)[1].strip()
        elif "image generate" in lower_text:
            prompt = message_text.lower().split("image generate", 1)[1].strip()
        
        if prompt:
            waiting_msg = await update.message.reply_text("Creating your picture please wait..")
            image_url = await generate_image(prompt)
            try:
                await waiting_msg.delete()
            except:
                pass
            
            if image_url:
                try:
                    await update.message.reply_photo(photo=image_url)
                    add_to_history(chat_id, "user", message_text)
                    add_to_history(chat_id, "assistant", f"[Generated image: {prompt}]")
                except Exception as e:
                    logger.error(f"Error sending image: {e}")
                    await update.message.reply_text("Image generation failed. Please try again later.")
            else:
                await update.message.reply_text("Image generation failed. Please try again later.")
            return
    
    # Get AI response (handles image generation internally)
    response = await get_ai_response(chat_id, message_text, update, context)
    
    if response:
        try:
            sent_msg = await update.message.reply_text(response, parse_mode='Markdown')
            last_bot_messages[chat_id] = sent_msg.message_id
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            try:
                sent_msg = await update.message.reply_text(response)
                last_bot_messages[chat_id] = sent_msg.message_id
            except:
                pass


async def reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle replies to bot's messages in groups."""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    if update.message.reply_to_message:
        replied_to_id = update.message.reply_to_message.message_id
        
        if chat_id in last_bot_messages and replied_to_id == last_bot_messages[chat_id]:
            message_text = update.message.text
            
            # Check for admin special trigger "who made you"
            if user_id == ADMIN_ID and message_text.strip().lower() == "who made you":
                await update.message.reply_text("Boss, I am a powerful AI and group helper created by you 💪")
                return
            
            # Check for direct image generation request
            lower_text = message_text.lower()
            if "pik generate" in lower_text or "image generate" in lower_text:
                prompt = ""
                if "pik generate" in lower_text:
                    prompt = message_text.lower().split("pik generate", 1)[1].strip()
                elif "image generate" in lower_text:
                    prompt = message_text.lower().split("image generate", 1)[1].strip()
                
                if prompt:
                    waiting_msg = await update.message.reply_text("Creating your picture please wait..")
                    image_url = await generate_image(prompt)
                    try:
                        await waiting_msg.delete()
                    except:
                        pass
                    
                    if image_url:
                        try:
                            await update.message.reply_photo(photo=image_url)
                            add_to_history(chat_id, "user", message_text)
                            add_to_history(chat_id, "assistant", f"[Generated image: {prompt}]")
                        except Exception as e:
                            logger.error(f"Error sending image: {e}")
                            await update.message.reply_text("Image generation failed. Please try again later.")
                    else:
                        await update.message.reply_text("Image generation failed. Please try again later.")
                    return
            
            # Get AI response (handles image generation internally)
            response = await get_ai_response(chat_id, message_text, update, context)
            
            if response:
                try:
                    sent_msg = await update.message.reply_text(response, parse_mode='Markdown')
                    last_bot_messages[chat_id] = sent_msg.message_id
                except Exception as e:
                    logger.error(f"Error sending message: {e}")
                    try:
                        sent_msg = await update.message.reply_text(response)
                        last_bot_messages[chat_id] = sent_msg.message_id
                    except:
                        pass


async def store_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Store original messages for edit detection."""
    if update.message:
        original_messages[update.message.message_id] = {
            "text": update.message.text or update.message.caption or "[Media/Non-text content]",
            "user": update.message.from_user,
            "chat_id": update.effective_chat.id
        }


async def deleted_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deleted messages."""
    # Note: Telegram Bot API doesn't provide content of deleted messages directly
    # We can only detect that a message was deleted if we tracked it before
    pass


async def edited_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle edited messages in groups."""
    if not update.edited_message:
        return
    
    chat_id = update.effective_chat.id
    message_id = update.edited_message.message_id
    new_text = update.edited_message.text or update.edited_message.caption or "[Media/Non-text content]"
    user = update.edited_message.from_user
    
    # Get old info if stored
    old_info = original_messages.get(message_id, {})
    old_text = old_info.get("text", "[Unknown original message]")
    old_user = old_info.get("user")
    
    # Update stored message
    original_messages[message_id] = {
        "text": new_text,
        "user": user,
        "chat_id": chat_id
    }
    
    # Only notify in groups, not private chats
    if update.effective_chat.type in ['group', 'supergroup']:
        user_display = f"@{user.username}" if user.username else user.full_name
        
        # Monospace format for helper output
        edit_notice = (
            f"```\n"
            f"MESSAGE EDITED\n"
            f"==============\n\n"
            f"User: {user_display}\n"
            f"User ID: {user.id}\n\n"
            f"ORIGINAL MESSAGE:\n"
            f"{old_text[:800]}{'...' if len(old_text) > 800 else ''}\n\n"
            f"EDITED MESSAGE:\n"
            f"{new_text[:800]}{'...' if len(new_text) > 800 else ''}\n"
            f"```"
        )
        
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=edit_notice,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send edit notice: {e}")


async def message_handler_for_delete_tracking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track messages for delete detection using bot's message handler."""
    # This is handled by store_message, but we need a way to detect deletions
    # Unfortunately, Telegram Bot API doesn't provide a direct way to know WHO deleted a message
    # We can only know a message was deleted via getUpdates, but not the deleter
    pass


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Update {update} caused error {context.error}")
    
    try:
        if update and update.effective_message:
            await update.effective_message.reply_text(
                "Sorry, an error occurred. Please try again later."
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")


def main():
    """Start the bot."""
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("ai", ai_command))
    
    # Store original messages for edit detection
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_message), group=1)
    
    # Reply handler for groups (check if replying to bot)
    application.add_handler(MessageHandler(
        filters.REPLY & filters.ChatType.GROUPS,
        reply_handler
    ), group=2)
    
    # Private chat handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE,
        private_chat_handler
    ), group=3)
    
    # Edited message handler
    application.add_handler(MessageHandler(
        filters.UpdateType.EDITED_MESSAGE,
        edited_message_handler
    ), group=4)
    
    # Error handler
    application.add_error_handler(error_handler)
    
    logger.info("Bot started! Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
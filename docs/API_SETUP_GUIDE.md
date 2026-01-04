# 🔑 API Keys Setup Guide

Welcome to Coach Aria! This guide will walk you through obtaining all the required API keys to run the project. All services used have **free tiers** that are more than enough to get started.

---

## Table of Contents

1. [Groq API Key](#1-groq-api-key) - For LLM, Vision, and Speech-to-Text
2. [ElevenLabs API Key](#2-elevenlabs-api-key) - For Text-to-Speech
3. [HuggingFace Token](#3-huggingface-token) - For Image Generation
4. [Qdrant Cloud](#4-qdrant-cloud) - For Vector Database (Long-term Memory)
5. [Final Setup](#5-final-setup)

---

## 1. Groq API Key

Groq provides blazing-fast LLM inference. We use it for:
- **Llama 3.3 70B** - Main conversational AI
- **Llama 4 Scout Vision** - Image understanding
- **Whisper Large v3 Turbo** - Speech-to-text

### Steps to Get Your Key:

1. Go to [console.groq.com](https://console.groq.com/)

2. Click **"Sign Up"** (or "Log In" if you have an account)
   - You can sign up with Google, GitHub, or email

3. Once logged in, go to **API Keys** in the left sidebar
   - Or directly visit: [console.groq.com/keys](https://console.groq.com/keys)

4. Click **"Create API Key"**

5. Give it a name (e.g., "coach-aria") and click **"Submit"**

6. **Copy the API key immediately** - you won't be able to see it again!

### Free Tier Limits:
- 14,400 requests/day for most models
- More than enough for personal use

---

## 2. ElevenLabs API Key

ElevenLabs provides natural-sounding text-to-speech voices.

### Steps to Get Your Key:

1. Go to [elevenlabs.io](https://elevenlabs.io/)

2. Click **"Sign Up"** in the top right
   - You can sign up with Google or email

3. Once logged in, click your profile icon (top right)

4. Select **"Profile + API key"** from the dropdown

5. You'll see your API key displayed. Click the **eye icon** to reveal it

6. **Copy the API key**

### Free Tier Limits:
- 10,000 characters/month
- Access to all voice models
- Enough for testing and demos

### Tip:
The project uses voice ID `IKne3meq5aSn9XLyUdCD` (a pre-made voice). You can change this in `modules/speech/text_to_speech.py` if you want a different voice.

---

## 3. HuggingFace Token

HuggingFace hosts the Stable Diffusion XL model for image generation.

### Steps to Get Your Token:

1. Go to [huggingface.co](https://huggingface.co/)

2. Click **"Sign Up"** in the top right
   - You can sign up with email or SSO

3. Once logged in, click your profile icon (top right)

4. Select **"Settings"**

5. In the left sidebar, click **"Access Tokens"**
   - Or directly visit: [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)

6. Click **"New token"**

7. Give it a name (e.g., "coach-aria")

8. Select **"Read"** as the token type (that's all we need)

9. Click **"Generate a token"**

10. **Copy the token** (starts with `hf_...`)

### Free Tier:
- Inference API has rate limits but is free
- Stable Diffusion XL works well within free tier

---

## 4. Qdrant Cloud

Qdrant is a vector database that stores and retrieves memories for the AI.

### Steps to Set Up:

1. Go to [cloud.qdrant.io](https://cloud.qdrant.io/)

2. Click **"Sign Up"** 
   - You can sign up with Google, GitHub, or email

3. Once logged in, you'll be in the Dashboard

4. Click **"Create Cluster"** (or "Create" button)

5. Choose the **Free Tier** option:
   - Select a region close to you
   - Keep default settings
   - Click **"Create"**

6. Wait for the cluster to be created (takes ~1 minute)

7. Once created, click on your cluster name

8. You'll see the **Cluster URL** - copy this (looks like `https://xxx-xxx.aws.cloud.qdrant.io`)

9. Go to **API Keys** tab

10. Click **"Create API Key"**

11. **Copy the API key**

### Free Tier Limits:
- 1GB storage
- 1M vectors
- More than enough for this project

---

## 5. Final Setup

Now that you have all your API keys, create a `.env` file in the project root:

### Create the .env file:

```bash
# In the project root directory, create a file named ".env"
```

### Add your keys to the .env file:

```env
# Groq - LLM, Vision, and STT
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ElevenLabs - Text-to-Speech
ELEVENLABS_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# HuggingFace - Image Generation
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Qdrant - Vector Database
QDRANT_URL=https://your-cluster-id.region.aws.cloud.qdrant.io
QDRANT_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### ⚠️ Important Notes:

1. **Never share your API keys** or commit them to version control
2. **Keep the .env file private** - it's already in `.gitignore`
3. Replace the placeholder values with your actual keys
4. Make sure there are **no spaces** around the `=` sign

---

## Quick Checklist

Before running the project, verify you have:

- [ ] Groq API Key
- [ ] ElevenLabs API Key  
- [ ] HuggingFace Token
- [ ] Qdrant Cluster URL
- [ ] Qdrant API Key
- [ ] Created `.env` file with all keys

---

## Running the Project

Once your `.env` file is set up:

```bash
# Install dependencies (if not already done)
pip install -r requirements.txt

# Run the application
chainlit run interfaces/chainlit/app.py -w
```

The app will be available at `http://localhost:8000`

---

## Troubleshooting

### "API Key not found" errors
- Make sure your `.env` file is in the project root directory
- Check that variable names match exactly (case-sensitive)
- Restart the application after adding/changing keys

### Groq rate limit errors
- Wait a few seconds and try again
- Free tier has generous limits but can hit them with heavy use

### ElevenLabs character limit
- Free tier has 10,000 chars/month
- Upgrade to a paid plan if needed, or use shorter responses

### Qdrant connection errors
- Verify your cluster URL includes `https://`
- Check that the cluster is running in Qdrant Cloud dashboard

---

## Need Help?

If you encounter any issues:
1. Double-check all API keys are correctly copied
2. Ensure no extra spaces or quotes around values
3. Verify your free tier hasn't expired

Enjoy using Coach Aria! 🎉

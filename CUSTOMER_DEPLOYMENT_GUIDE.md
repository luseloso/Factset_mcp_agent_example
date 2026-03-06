# Deploying Your FactSet Agent: A Step-by-Step Guide! 🚀

Welcome! This guide is designed to be incredibly simple. We are going to deploy your cutting-edge FactSet AI Agent into Gemini Enterprise in just two easy steps. 

Think of this process like building a Lego robot:
1. **First, we build the robot's brain** in Google Cloud (the `Reasoning Engine`).
2. **Second, we plug the robot into your FactSet account** and turn it on in Gemini Enterprise!

Let's begin!

---

## Step 1: Building the Robot's Brain 🧠

Before the agent can do any financial math or call FactSet, we need to upload its code to Vertex AI in Google Cloud.

1. Open your computer's terminal and navigate to this folder where your files are.
2. Important: Copy the `config.json.example` file to create a new file named `config.json` and paste your FactSet JWK authentication data inside it. *(The system needs this to run a one-time scan of the tools!)*
3. Make sure you are authenticated with Google Cloud by running:
   ```bash
   gcloud auth application-default login
   ```
4. Type the following command and hit Enter:
   ```bash
   python agent_engine.py
   ```
4. **Wait for about 10 minutes!** Google Cloud is packing your code into a special container. 
5. When it finishes, your terminal will print out a green success message that says `Agent Engine updated. Resource name: projects/.../reasoningEngines/1234567890`.
6. **Copy that long `projects/...` string and save it!** This is your new Agent's unique "Brain ID".

---

## Step 2: Giving the Robot its FactSet Keys 🔑

Now that the brain is built, we need to securely hand it your FactSet API keys and plug it into Gemini Enterprise so you can chat with it.

We have created a magical, automated script to do this for you called `deploy_gemini_enterprise.sh`.

1. Open the file `deploy_gemini_enterprise.sh` in any text editor.
2. At the very top, you will see a `VARIABLES` section with `<YOUR_...>` placeholders. Fill in the blanks:
   - **`PROJECT_ID`**: Your Google Cloud project name.
   - **`PROJECT_NUMBER`**: Your Google Cloud numerical ID.
   - **`AS_APP`**: Your Gemini Enterprise instance ID.
   - **`CLIENT_ID` / `CLIENT_SECRET`**: Your FactSet MCP credentials.
   - **`REASONING_ENGINE_RES`**: Paste the long "Brain ID" string you copied at the end of Step 1!
3. Save the file.
4. Back in your terminal, run this command:
   ```bash
   bash deploy_gemini_enterprise.sh
   ```
5. You will see fireworks in your terminal as it registers your FactSet Oauth Connection securely into the Cloud and automatically maps the Agent to your Gemini Chat Window!

---

## Step 3: Start Chatting! 🎉

You did it! 

Go open your **Gemini Enterprise web browser window**. You will notice that a brand new Agent (e.g., `Factset_MCP_Agent`) has been dynamically added to your workspace. 

Type something like:
> *"What were Apple's revenues last year?"*

The agent will seamlessly extract your user profile, authenticate against FactSet's servers automatically using the keys we just set up, download the exact financial data without hallucinating, and print out a gorgeous Markdown table for you!

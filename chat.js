const character = JSON.parse(sessionStorage.getItem("selectedCharacter"));
const chatLog = document.getElementById("chat-log");
const userInput = document.getElementById("user-input");
const sendButton = document.getElementById("send-button");

const KOBOLD_API_URL = "http://127.0.0.1:5000/api/v1/generate";
const TTS_API_URL = "http://127.0.0.1:8000/api/tts";

function addMessage(sender, text) {
    const messageContainer = document.createElement("div");
    messageContainer.classList.add("message-container", sender);

    const textBubble = document.createElement("div");
    textBubble.classList.add("text-bubble");
    textBubble.innerHTML = `<strong>${sender === "user" ? "You" : character.name}:</strong> ${text}`;

    messageContainer.appendChild(textBubble);
    chatLog.appendChild(messageContainer);
    chatLog.scrollTop = chatLog.scrollHeight;
}

async function sendMessage() {
    const userMessage = userInput.value.trim();
    if (!userMessage) return;

    addMessage("user", userMessage);

    // Send prompt to Kobold API
    const prompt = `${character.description}\n\nUser: ${userMessage}\n${character.name}:`;
    const koboldResponse = await fetch(KOBOLD_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            max_context_length: 2048,
            max_length: 150,
            prompt: prompt,
            temperature: 0.7,
            top_p: 0.9,
            rep_pen: 1.1,
            rep_pen_range: 256
        })
    });

    const responseData = await koboldResponse.json();
    const botMessage = responseData.results[0].text.trim();

    addMessage("bot", botMessage);

    // Send text to TTS-RVC Flask API
    const ttsResponse = await fetch(TTS_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            text: botMessage,
            voice: character.ttsVoice
        })
    });

    const ttsData = await ttsResponse.json();
    const audioUrl = ttsData.audio_url;

    // Play the audio response
    const audio = new Audio(audioUrl);
    audio.play();

    userInput.value = ""; // Clear input field
}

sendButton.addEventListener("click", sendMessage);

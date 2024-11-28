const character = JSON.parse(sessionStorage.getItem("selectedCharacter"));
const chatLog = document.getElementById("chat-log");
const userInput = document.getElementById("user-input");
const sendButton = document.getElementById("send-button");

// Chat history for context
let chatHistory = [];
const MAX_HISTORY_LENGTH = 10;  // Maximum number of exchanges to keep

// Audio state
let audioEnabled = true;
let autoplayEnabled = true;
let currentAudioPlayer = null;
let currentAudioUrl = null;

// Helper function for TTS text filtering
function filterTextForTTS(text) {
    return text.replace(/\*[^*]*\*/g, '').trim();
}

// Initialize UI
document.getElementById("character-name").textContent = character.name;
document.getElementById("character-description").textContent = character.description;

// Add character avatar
const avatarContainer = document.createElement("div");
avatarContainer.className = "chat-header-avatar"; // Changed class name
const avatarImg = document.createElement("img");
avatarImg.src = "../" + character.avatar;
avatarImg.alt = character.name;
avatarContainer.appendChild(avatarImg);
document.querySelector("header").appendChild(avatarContainer);

// Add audio controls
const audioToggle = document.createElement("button");
audioToggle.className = "audio-toggle";
audioToggle.innerHTML = "🔊";
audioToggle.onclick = () => {
    audioEnabled = !audioEnabled;
    audioToggle.innerHTML = audioEnabled ? "🔊" : "🔇";
    if (!audioEnabled && currentAudioPlayer) {
        currentAudioPlayer.pause();
        currentAudioPlayer.remove();
        currentAudioPlayer = null;
        currentAudioUrl = null;
    }
};
document.querySelector("header").appendChild(audioToggle);

const CHAT_API_URL = "http://136.38.129.228:51080/api/chat/completions";
const TTS_API_URL = "http://136.38.129.228:51080/api/tts";

function addMessage(sender, text) {
    console.log("Adding message:", sender, text);
    const messageContainer = document.createElement("div");
    messageContainer.classList.add("message-container", sender);

    // Add avatar
    const avatarDiv = document.createElement("div");
    avatarDiv.classList.add("message-avatar");
    const avatarImg = document.createElement("img");
    // Update the avatar path in the addMessage function
    avatarImg.src = sender === "user" ? "../avatars/default-user.png" : "../" + character.avatar;
    avatarImg.alt = sender === "user" ? "You" : character.name;
    avatarDiv.appendChild(avatarImg);

    const textBubble = document.createElement("div");
    textBubble.classList.add("text-bubble");
    textBubble.innerHTML = text.replace(/\*(.*?)\*/g, '<em>$1</em>'); // Convert asterisks to italics

    // Order elements based on sender
    if (sender === "user") {
        messageContainer.appendChild(textBubble);
        messageContainer.appendChild(avatarDiv);
    } else {
        messageContainer.appendChild(avatarDiv);
        messageContainer.appendChild(textBubble);
    }

    chatLog.appendChild(messageContainer);
    chatLog.scrollTop = chatLog.scrollHeight;

    // Update chat history
    chatHistory.push({ role: sender === "user" ? "user" : "assistant", content: text });
    if (chatHistory.length > MAX_HISTORY_LENGTH * 2) {
        chatHistory.splice(0, 2);
    }
    
    console.log("Current chat history:", chatHistory);
}

async function playAudio(audioUrl) {
    if (!audioEnabled) return;

    // If this audio is already playing, don't start it again
    if (currentAudioUrl === audioUrl) {
        console.log("Audio already playing:", audioUrl);
        return;
    }

    console.log("Playing new audio:", audioUrl);
    currentAudioUrl = audioUrl;

    // Stop any currently playing audio
    if (currentAudioPlayer) {
        currentAudioPlayer.pause();
        currentAudioPlayer.remove();
        currentAudioPlayer = null;
    }

    // Remove any existing audio controls
    const existingControls = document.querySelector('.audio-controls');
    if (existingControls) {
        existingControls.remove();
    }

    const audioControls = document.createElement("div");
    audioControls.className = "audio-controls";
    
    const playButton = document.createElement("button");
    playButton.innerHTML = "▶️";
    playButton.title = "Play/Pause";
    
    const autoplayButton = document.createElement("button");
    autoplayButton.innerHTML = autoplayEnabled ? "🔄" : "⏸️";
    autoplayButton.title = "Toggle Autoplay";
    
    const closeButton = document.createElement("button");
    closeButton.innerHTML = "✖️";
    closeButton.title = "Close";

    audioControls.appendChild(playButton);
    audioControls.appendChild(autoplayButton);
    audioControls.appendChild(closeButton);
    document.body.appendChild(audioControls);

    const audioPlayer = document.createElement("audio");
    audioPlayer.src = audioUrl;
    currentAudioPlayer = audioPlayer;

    playButton.onclick = () => {
        if (audioPlayer.paused) {
            audioPlayer.play();
            playButton.innerHTML = "⏸️";
        } else {
            audioPlayer.pause();
            playButton.innerHTML = "▶️";
        }
    };

    autoplayButton.onclick = () => {
        autoplayEnabled = !autoplayEnabled;
        autoplayButton.innerHTML = autoplayEnabled ? "🔄" : "⏸️";
    };

    closeButton.onclick = () => {
        audioPlayer.pause();
        audioControls.remove();
        currentAudioPlayer = null;
        currentAudioUrl = null;
    };

    if (autoplayEnabled) {
        try {
            await audioPlayer.play();
            playButton.innerHTML = "⏸️";
        } catch (error) {
            console.error("Audio playback error:", error);
            playButton.innerHTML = "▶️";
        }
    }

    audioPlayer.onended = () => {
        playButton.innerHTML = "▶️";
        currentAudioUrl = null;
    };

    audioPlayer.onerror = () => {
        console.error("Audio playback error");
        audioControls.remove();
        currentAudioPlayer = null;
        currentAudioUrl = null;
    };
}

async function sendMessage() {
    try {
        const userMessage = userInput.value.trim();
        if (!userMessage) return;

        console.log("Sending message:", userMessage);
        addMessage("user", userMessage);
        userInput.value = "";
        
        userInput.disabled = true;
        sendButton.disabled = true;

        const messages = [
            { 
                role: "system", 
                content: character.systemPrompt || `You are ${character.name}. ${character.description}`
            },
            ...chatHistory.map(msg => ({
                role: msg.role,
                content: msg.content
            })),
            { role: "user", content: userMessage }
        ];

        const requestBody = {
            model: "koboldcpp",
            messages: messages,
            temperature: 0.75,
            max_tokens: 60,
            top_p: 0.9,
            presence_penalty: 0.6,
            frequency_penalty: 0.3
        };

        console.log("Sending to chat API:", requestBody);
        console.log("Current context length:", messages.length);

        const response = await fetch(CHAT_API_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        const responseData = await response.json();
        console.log("API response:", responseData);

        if (!responseData.choices || !responseData.choices[0] || !responseData.choices[0].message) {
            throw new Error("Invalid response format from API");
        }

        const botMessage = responseData.choices[0].message.content.trim();
        console.log("Bot message:", botMessage);
        
        addMessage("bot", botMessage);

        // Handle TTS with filtered text
        try {
            const ttsText = filterTextForTTS(botMessage);
            if (ttsText) {
                const ttsResponse = await fetch(TTS_API_URL, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        text: ttsText,
                        edge_voice: character.ttsVoice,
                        rvc_model: character.id
                    })
                });

                if (!ttsResponse.ok) {
                    throw new Error(`TTS API error: ${ttsResponse.status}`);
                }

                const ttsData = await ttsResponse.json();
                console.log("TTS response:", ttsData);
                
                const audioUrl = `http://136.38.129.228:51080${ttsData.audio_url}`;
                console.log("Playing audio from URL:", audioUrl);
                await playAudio(audioUrl);
            }
        } catch (error) {
            console.error("TTS error:", error);
        }

    } catch (error) {
        console.error("Error details:", error.message);
        console.error("Full error:", error);
        addMessage("bot", "I apologize, there was an error processing your message.");
    } finally {
        userInput.disabled = false;
        sendButton.disabled = false;
        userInput.focus();
    }
}

// Add event listeners when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log("Chat interface initializing...");
    console.log("Character loaded:", character);

    sendButton.addEventListener("click", sendMessage);
    userInput.addEventListener("keypress", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            sendMessage();
        }
    });
    
    userInput.focus();
    
    console.log("Chat interface initialized");
});
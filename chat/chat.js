// Configuration and state management
const character = JSON.parse(sessionStorage.getItem("selectedCharacter"));
const chatLog = document.getElementById("chat-log");
const userInput = document.getElementById("user-input");
const sendButton = document.getElementById("send-button");

// API endpoints
const CHAT_API_URL = "/v1/chat/completions";
const TTS_API_URL = "/v1/tts";
const TRANSCRIBE_API_URL = "/api/transcribe";

// Chat state
let chatHistory = [];
const MAX_HISTORY_LENGTH = 10;
let messageQueue = [];
const MAX_QUEUE_SIZE = 5;
let isProcessing = false;

// Audio state
let audioEnabled = true;
let autoplayEnabled = true;
let currentAudioPlayer = null;
let currentAudioUrl = null;

// Helper Functions
function filterTextForTTS(text) {
    return text.replace(/\*[^*]*\*/g, '').trim();
}

// Initialize UI
function initializeUI() {
    try {
        document.getElementById("character-name").textContent = character.name;
        document.getElementById("character-description").textContent = character.description;

        // Add character avatar
        const avatarContainer = document.createElement("div");
        avatarContainer.className = "chat-header-avatar";
        const avatarImg = document.createElement("img");
        avatarImg.src = "../" + character.avatar;
        avatarImg.alt = character.name;
        avatarContainer.appendChild(avatarImg);
        document.querySelector("header").appendChild(avatarContainer);

        // Add audio toggle
        const audioToggle = document.createElement("button");
        audioToggle.className = "audio-toggle";
        audioToggle.innerHTML = "🔊";
        audioToggle.onclick = toggleAudio;
        document.querySelector("header").appendChild(audioToggle);

        // Add clear chat button
        const clearButton = document.createElement("button");
        clearButton.className = "clear-chat";
        clearButton.innerHTML = "Clear Chat";
        clearButton.onclick = clearChatState;
        document.querySelector("header").appendChild(clearButton);
    } catch (error) {
        console.error("Error initializing UI:", error);
        const header = document.querySelector('header');
        if (header) {
            const errorMessage = document.createElement('div');
            errorMessage.className = 'error-message';
            errorMessage.textContent = 'Error initializing chat. Please refresh the page.';
            header.appendChild(errorMessage);
        }
    }
}

function toggleAudio() {
    audioEnabled = !audioEnabled;
    const audioToggle = document.querySelector('.audio-toggle');
    if (audioToggle) {
        audioToggle.innerHTML = audioEnabled ? "🔊" : "🔇";
    }
    if (!audioEnabled && currentAudioPlayer) {
        currentAudioPlayer.pause();
        currentAudioPlayer = null;
        currentAudioUrl = null;
    }
}

function clearChatState() {
    chatHistory = [];
    messageQueue = [];
    isProcessing = false;
    
    if (currentAudioPlayer) {
        currentAudioPlayer.pause();
        currentAudioPlayer = null;
        currentAudioUrl = null;
    }
    
    const existingControls = document.querySelector('.audio-controls');
    if (existingControls) {
        existingControls.remove();
    }
    
    if (chatLog) {
        chatLog.innerHTML = '';
    }
}
function addMessage(sender, text) {
    const messageContainer = document.createElement("div");
    messageContainer.classList.add("message-container", sender);

    const avatarDiv = document.createElement("div");
    avatarDiv.classList.add("message-avatar");
    const avatarImg = document.createElement("img");
    avatarImg.src = sender === "user" ? "../avatars/default-user.png" : "../" + character.avatar;
    avatarImg.alt = sender === "user" ? "You" : character.name;
    avatarDiv.appendChild(avatarImg);

    const textBubble = document.createElement("div");
    textBubble.classList.add("text-bubble");
    textBubble.innerHTML = text.replace(/\*(.*?)\*/g, '<em>$1</em>');

    if (sender === "user") {
        messageContainer.appendChild(textBubble);
        messageContainer.appendChild(avatarDiv);
    } else {
        messageContainer.appendChild(avatarDiv);
        messageContainer.appendChild(textBubble);
    }

    chatLog.appendChild(messageContainer);
    chatLog.scrollTop = chatLog.scrollHeight;

    chatHistory.push({ role: sender === "user" ? "user" : "assistant", content: text });
    if (chatHistory.length > MAX_HISTORY_LENGTH * 2) {
        chatHistory = chatHistory.slice(-MAX_HISTORY_LENGTH * 2);
    }
}

async function sendMessage(userMessage = null) {
    if (isProcessing) {
        console.log("Already processing a message, please wait...");
        return;
    }

    try {
        const message = userMessage || userInput.value.trim();
        if (!message) return;

        isProcessing = true;
        if (!userMessage) {
            addMessage("user", message);
            userInput.value = "";
        }
        
        userInput.disabled = true;
        sendButton.disabled = true;

        const messages = [
            { 
                role: "system", 
                content: character.systemPrompt || `You are ${character.name}. ${character.description}`
            },
            ...chatHistory.slice(-MAX_HISTORY_LENGTH * 2).map(msg => ({
                role: msg.role,
                content: msg.content
            })),
            { role: "user", content: message }
        ];

        const requestBody = {
            model: "koboldcpp",
            messages: messages,
            temperature: 0.5,
            max_tokens: 250,
            top_p: 0.9,
            presence_penalty: 0.6,
            frequency_penalty: 0.6
        };

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
        if (!responseData.choices?.[0]?.message) {
            throw new Error("Invalid response format from API");
        }

        const botMessage = responseData.choices[0].message.content.trim();
        addMessage("bot", botMessage);

        // Handle TTS
        if (audioEnabled) {
            const ttsText = filterTextForTTS(botMessage);
            if (ttsText) {
                messageQueue.push(ttsText);
                if (messageQueue.length === 1) {
                    processNextInQueue();
                }
            }
        }

    } catch (error) {
        console.error("Error details:", error);
        addMessage("bot", "I apologize, there was an error. Please try clearing the chat and starting again.");
    } finally {
        isProcessing = false;
        userInput.disabled = false;
        sendButton.disabled = false;
        userInput.focus();
    }
}
async function processNextInQueue() {
    if (messageQueue.length === 0) return;

    try {
        const text = messageQueue[0];
        const requestBody = {
            text: text,
            edge_voice: character.ttsVoice,
            rvc_model: character.id,
            tts_rate: character.tts_rate || 0,
            rvc_pitch: character.rvc_pitch || 0
        };
        
        console.log("TTS Request:", requestBody);  // Debug log

        const ttsResponse = await fetch(TTS_API_URL, {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(requestBody)
        });

        if (!ttsResponse.ok) {
            throw new Error(`TTS API error: ${ttsResponse.status}`);
        }

        const ttsData = await ttsResponse.json();
        console.log("TTS Response:", ttsData);  // Debug log
        
        if (!ttsData.audio_url) {
            throw new Error("No audio URL received from TTS service");
        }

        const audioUrl = ttsData.audio_url;
        console.log("Audio URL:", audioUrl);  // Debug log
        
        if (audioUrl) {
            await playAudio(audioUrl);
        } else {
            throw new Error("No audio URL received from TTS service");
        }

    } catch (error) {
        console.error("TTS error:", error);
        messageQueue.shift(); // Remove failed message from queue
    } finally {
        messageQueue.shift();
        if (messageQueue.length > 0) {
            processNextInQueue();
        }
    }
}

async function playAudio(audioUrl) {
    if (!audioEnabled) return;

    try {
        if (currentAudioUrl === audioUrl) {
            console.log("Audio already playing:", audioUrl);
            return;
        }

        if (currentAudioPlayer) {
            currentAudioPlayer.pause();
            currentAudioPlayer = null;
        }

        const existingControls = document.querySelector('.audio-controls');
        if (existingControls) {
            existingControls.remove();
        }

        const audioControls = document.createElement("div");
        audioControls.className = "audio-controls";
        
        const playButton = document.createElement("button");
        playButton.innerHTML = "⏸️";  // Start with pause since we'll autoplay
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

        const audioPlayer = new Audio(audioUrl);
        currentAudioPlayer = audioPlayer;
        currentAudioUrl = audioUrl;

        // Set up event listeners
        playButton.onclick = () => {
            if (audioPlayer.paused) {
                audioPlayer.play()
                    .then(() => playButton.innerHTML = "⏸️")
                    .catch(console.error);
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

        // Set up audio event listeners
        audioPlayer.onended = () => {
            playButton.innerHTML = "▶️";
            currentAudioUrl = null;
        };

        audioPlayer.onerror = (e) => {
            console.error("Audio playback error:", e);
            audioControls.remove();
            currentAudioPlayer = null;
            currentAudioUrl = null;
        };

        // Start playing if autoplay is enabled
        if (autoplayEnabled) {
            try {
                await audioPlayer.play();
                playButton.innerHTML = "⏸️";
            } catch (error) {
                console.error("Audio autoplay error:", error);
                playButton.innerHTML = "▶️";
            }
        }

    } catch (error) {
        console.error("Error in playAudio:", error);
        const existingControls = document.querySelector('.audio-controls');
        if (existingControls) {
            existingControls.remove();
        }
    }
}

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    try {
        initializeUI();
        
        if (sendButton && userInput) {
            sendButton.addEventListener("click", () => sendMessage());
            userInput.addEventListener("keypress", (event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    sendMessage();
                }
            });
            
            userInput.focus();
        }
    } catch (error) {
        console.error('Error initializing chat:', error);
        showInitializationError(error);
    }
});
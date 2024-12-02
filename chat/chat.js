// Configuration and state management
const character = JSON.parse(sessionStorage.getItem("selectedCharacter"));
const chatLog = document.getElementById("chat-log");
const userInput = document.getElementById("user-input");
const sendButton = document.getElementById("send-button");

// API endpoints
const CHAT_API_URL = "/v1/chat/completions";
const TTS_API_URL = "/v1/tts";

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
        // Set character info
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

        // Add background image
        const backgroundImg = document.querySelector(".chat-background");
        const backgroundPath = `../characters/${character.id}/background.jpg`;
        
        // Check if background image exists
        fetch(backgroundPath)
            .then(response => {
                if (response.ok) {
                    backgroundImg.src = backgroundPath;
                } else {
                    backgroundImg.src = "../assets/images/default-background.jpg";
                }
            })
            .catch(() => {
                backgroundImg.src = "../assets/images/default-background.jpg";
            });

        // Add audio toggle
        const audioToggle = document.querySelector('.audio-toggle');
        if (audioToggle) {
            audioToggle.onclick = toggleAudio;
        }

        // Add clear chat button
        const clearButton = document.querySelector('.clear-chat');
        if (clearButton) {
            clearButton.onclick = clearChatState;
        }

        // Initialize greeting
        setTimeout(sendInitialGreeting, 1000);

    } catch (error) {
        console.error("Error initializing UI:", error);
        showInitializationError(error);
    }
}

function sendInitialGreeting() {
    const hour = new Date().getHours();
    let timeGreeting = '';
    
    if (hour < 12) {
        timeGreeting = 'Good morning';
    } else if (hour < 18) {
        timeGreeting = 'Good afternoon';
    } else {
        timeGreeting = 'Good evening';
    }

    // Add debug logging
    console.log("Character data:", character);
    console.log("Greetings array:", character.greetings);

    let characterGreeting = "Hello! How can I help you today?";

    if (character.greetings && Array.isArray(character.greetings) && character.greetings.length > 0) {
        characterGreeting = character.greetings[Math.floor(Math.random() * character.greetings.length)];
    } else {
        console.log("No valid greetings found in character data");
    }

    const fullGreeting = `${timeGreeting}! ${characterGreeting}`;
    addMessage("bot", fullGreeting);

    if (audioEnabled) {
        const ttsText = filterTextForTTS(fullGreeting);
        if (ttsText) {
            messageQueue.push(ttsText);
            if (messageQueue.length === 1) {
                processNextInQueue();
            }
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
    
    if (chatLog) {
        chatLog.innerHTML = '';
    }

    // Resend initial greeting after clearing
    setTimeout(sendInitialGreeting, 500);
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

        // Default AI parameters
        const defaultParams = {
            temperature: 0.7,
            max_tokens: 150,
            top_p: 0.9,
            presence_penalty: 0.6,
            frequency_penalty: 0.6
        };

        // Merge with character-specific parameters if they exist
        const aiParams = {
            ...defaultParams,
            ...character.ai_parameters // This will override defaults only if they exist
        };

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
            ...aiParams // Spread the merged parameters
        };

        console.log("Sending request with parameters:", aiParams);

        const response = await fetch(CHAT_API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
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

        const ttsResponse = await fetch(TTS_API_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestBody)
        });

        if (!ttsResponse.ok) {
            throw new Error(`TTS API error: ${ttsResponse.status}`);
        }

        const ttsData = await ttsResponse.json();
        
        if (!ttsData.audio_url) {
            throw new Error("No audio URL received from TTS service");
        }

        const audioUrl = ttsData.audio_url;
        
        if (audioUrl) {
            await playAudio(audioUrl);
        }

    } catch (error) {
        console.error("TTS error:", error);
        messageQueue.shift();
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

        const audioPlayer = new Audio(audioUrl);
        currentAudioPlayer = audioPlayer;
        currentAudioUrl = audioUrl;

        if (autoplayEnabled) {
            try {
                await audioPlayer.play();
            } catch (error) {
                console.error("Audio autoplay error:", error);
            }
        }

        audioPlayer.onended = () => {
            currentAudioUrl = null;
        };

        audioPlayer.onerror = (e) => {
            console.error("Audio playback error:", e);
            currentAudioPlayer = null;
            currentAudioUrl = null;
        };

    } catch (error) {
        console.error("Error in playAudio:", error);
    }
}

function showInitializationError(error) {
    const header = document.querySelector('header');
    if (header) {
        const errorMessage = document.createElement('div');
        errorMessage.className = 'error-message';
        errorMessage.textContent = 'Error initializing chat. Please refresh the page.';
        header.appendChild(errorMessage);
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
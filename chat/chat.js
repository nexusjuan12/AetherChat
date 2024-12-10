// Configuration and state management
let currentUser = null;
const character = JSON.parse(sessionStorage.getItem("selectedCharacter"));
const chatLog = document.getElementById("chat-log");
const userInput = document.getElementById("user-input");
const sendButton = document.getElementById("send-button");

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

// Background state and configurations
const backgroundImg = document.querySelector(".chat-background");
const videoFormats = ['mp4', 'webm', 'wmv'];
const imageFormats = ['webp', 'gif', 'jpg', 'png'];
const allFormats = [...videoFormats, ...imageFormats];

// Helper Functions
function filterTextForTTS(text) {
    return text.replace(/\*[^*]*\*/g, '').trim();
}

function sendInitialGreeting() {
    const hour = new Date().getHours();
    let timeGreeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

    console.log("Sending initial greeting...");
    
    // Check if greetings array exists and has items
    let characterGreeting = "Hello! How can I help you today?"; // Default greeting
    if (character.greetings && Array.isArray(character.greetings) && character.greetings.length > 0) {
        characterGreeting = character.greetings[Math.floor(Math.random() * character.greetings.length)];
    }

    // Add initial greeting to chat history
    const systemMessage = {
        role: "system",
        content: character.systemPrompt
    };
    
    const assistantMessage = {
        role: "assistant",
        content: characterGreeting
    };
    
    chatHistory.push(systemMessage, assistantMessage);
    
    const fullGreeting = `${timeGreeting}! ${characterGreeting}`;
    addMessage("bot", fullGreeting);

    if (audioEnabled) {
        const ttsText = filterTextForTTS(fullGreeting);
        if (ttsText) {
            console.log("Adding greeting to message queue:", ttsText);
            messageQueue = [ttsText]; // Reset queue and add greeting
            console.log("Current message queue:", messageQueue);
        }
    }
}

function toggleAudio() {
    audioEnabled = !audioEnabled;
    console.log("Audio enabled:", audioEnabled);
    const audioToggle = document.querySelector('.audio-toggle');
    if (audioToggle) {
        audioToggle.innerHTML = audioEnabled ? "🔊" : "🔇";
        const creditsPerMessage = audioEnabled ? "15" : "10";
        audioToggle.title = `Credits per message: ${creditsPerMessage}`;
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

    // Only add to chat history if it's not already from initialization
    if (sender === "user" || chatHistory.length === 0) {
        chatHistory.push({ 
            role: sender === "user" ? "user" : "assistant", 
            content: text 
        });

        if (chatHistory.length > MAX_HISTORY_LENGTH * 2) {
            chatHistory = chatHistory.slice(-MAX_HISTORY_LENGTH * 2);
        }
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

        const creditCost = audioEnabled ? 15 : 10;

        // Ensure system prompt is included
        let messages = chatHistory;
        if (!chatHistory.some(msg => msg.role === "system")) {
            messages = [
                {
                    role: "system",
                    content: character.systemPrompt
                },
                ...chatHistory
            ];
        }

        const response = await fetch('/v1/chat/completions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                model: "koboldcpp",
                messages: messages,
                temperature: character.ai_parameters?.temperature || 0.7,
                max_tokens: character.ai_parameters?.max_tokens || 150,
                top_p: character.ai_parameters?.top_p || 0.9,
                presence_penalty: character.ai_parameters?.presence_penalty || 0.6,
                frequency_penalty: character.ai_parameters?.frequency_penalty || 0.6
            })
        });

        if (response.status === 402) {
            addMessage("bot", "Insufficient credits. Please purchase more credits to continue chatting.");
            return;
        }

        if (!response.ok) {
            throw new Error(`API error: ${response.status}`);
        }

        const responseData = await response.json();
        const botMessage = responseData.choices[0].message.content.trim();
        addMessage("bot", botMessage);

        if (currentUser) {
            currentUser.user.credits -= creditCost;
            updateCreditDisplay();
        }

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
        addMessage("bot", "I apologize, there was an error. Please try again.");
    } finally {
        isProcessing = false;
        userInput.disabled = false;
        sendButton.disabled = false;
        userInput.focus();
    }
}

async function processNextInQueue() {
    if (messageQueue.length === 0) {
        console.log("Message queue is empty");
        return;
    }

    try {
        const text = messageQueue[0];
        console.log("Processing TTS for text:", text);
        console.log("Current character:", character);
        console.log("Audio enabled:", audioEnabled);
        
        const requestBody = {
            text: text,
            edge_voice: character.ttsVoice,
            rvc_model: character.id,
            tts_rate: character.tts_rate || 0,
            rvc_pitch: character.rvc_pitch || 0
        };

        console.log("Sending TTS request:", requestBody);

        const ttsResponse = await fetch('/v1/tts', {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(requestBody)
        });

        if (!ttsResponse.ok) {
            throw new Error(`TTS API error: ${ttsResponse.status}`);
        }

        const ttsData = await ttsResponse.json();
        console.log("TTS response:", ttsData);
        
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

        try {
            await audioPlayer.play();
        } catch (error) {
            console.error("Audio autoplay error:", error);
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
async function initializeUI() {
    try {
        // Check authentication first
        if (!await checkAuth()) return;

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

        // Load background
        await tryLoadBackground();

        // Setup start chat button
        const startChatOverlay = document.getElementById('start-chat-overlay');
        const startChatButton = document.getElementById('start-chat-button');
        const chatInput = document.querySelector('.chat-input');

        if (startChatButton && chatInput) {
            chatInput.style.display = 'none'; // Hide chat input initially
            startChatButton.addEventListener('click', () => {
                console.log("Start chat clicked, message queue:", messageQueue);
                startChatOverlay.style.display = 'none';
                chatInput.style.display = 'flex';
                userInput.focus();
                
                // Only process queue if audio is enabled
                if (audioEnabled && messageQueue.length > 0) {
                    console.log("Processing initial greeting audio");
                    processNextInQueue();
                }
            });
        }

        // Add audio toggle
        const audioToggle = document.querySelector('.audio-toggle');
        if (audioToggle) {
            audioToggle.onclick = toggleAudio;
            audioToggle.title = `Credits per message: ${audioEnabled ? "15" : "10"}`;
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

async function checkAuth() {
    try {
        const response = await fetch('/auth/user');
        if (!response.ok) {
            window.location.href = '/login.html';
            return false;
        }
        currentUser = await response.json();
        updateCreditDisplay();
        return true;
    } catch (error) {
        console.error('Auth check failed:', error);
        window.location.href = '/login.html';
        return false;
    }
}

function updateCreditDisplay() {
    const headerText = document.querySelector('.header-text');
    let creditDisplay = document.querySelector('.credit-display');
    if (!creditDisplay) {
        creditDisplay = document.createElement('div');
        creditDisplay.className = 'credit-display';
        headerText.appendChild(creditDisplay);
    }
    creditDisplay.innerHTML = `Credits: ${currentUser.user.credits}`;
}

// Background loading function
// Background loading function
async function tryLoadBackground() {
    const backgroundContainer = document.querySelector(".chat-background").parentNode;
    const checkPath = `../characters/${character.id}`;
    
    try {
        // Use fetch with HEAD method to efficiently check for file existence
        const fileTypes = ['png', 'jpg', 'gif', 'webp', 'mp4', 'webm'];
        
        for (const type of fileTypes) {
            const response = await fetch(`${checkPath}/background.${type}`, { method: 'HEAD' });
            if (response.ok) {
                const backgroundUrl = `${checkPath}/background.${type}`;
                
                if (videoFormats.includes(type)) {
                    const video = document.createElement('video');
                    video.className = 'chat-background';
                    video.src = backgroundUrl;
                    
                    // Essential video attributes for silent background
                    video.muted = true;
                    video.defaultMuted = true;
                    video.autoplay = true;
                    video.loop = true;
                    video.playsInline = true;
                    video.volume = 0;
                    video.setAttribute('muted', '');
                    video.setAttribute('playsinline', '');
                    
                    if (backgroundImg && backgroundImg.style) {
                        video.style = backgroundImg.style;
                    }
                    
                    backgroundContainer.replaceChild(video, backgroundImg);
                } else {
                    backgroundImg.src = backgroundUrl;
                }
                return;
            }
        }
        // If no background found, use default
        throw new Error('No background found');
    } catch (error) {
        console.log('Failed to load character background:', error);
        backgroundImg.src = "../assets/images/default-background.jpg";
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

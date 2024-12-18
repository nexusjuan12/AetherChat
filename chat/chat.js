// Audio state
let audioEnabled = true;
let autoplayEnabled = true;
let currentAudioPlayer = null;
let currentAudioUrl = null;
let isAudioPlaying = false;
let audioQueue = [];

// Configuration and state management
let currentUser = null;
const character = JSON.parse(sessionStorage.getItem("selectedCharacter"));
const chatLog = document.getElementById("chat-log");
const userInput = document.getElementById("user-input");
const sendButton = document.getElementById("send-button");

// New parameter state management
let sessionParameters = {
    voice: {
        rvcPitch: character.rvc_pitch || 0,
        ttsRate: character.tts_rate || 0
    },
    ai: {
        temperature: character.ai_parameters?.temperature || 0.7,
        topP: character.ai_parameters?.top_p || 0.9,
        presencePenalty: character.ai_parameters?.presence_penalty || 0.6,
        frequencyPenalty: character.ai_parameters?.frequency_penalty || 0.6
    }
};

// Parameter Management Functions
function initializeParameters() {
    console.log("Initializing parameters from character:", character);

    // Setup all parameter controls
    const parameterControls = {
        'rvc-pitch': {
            value: character.rvc_pitch || 0,
            updateFn: (value) => character.rvc_pitch = value
        },
        'tts-rate': {
            value: character.tts_rate || 0,
            updateFn: (value) => character.tts_rate = value
        },
        'temperature': {
            value: character.ai_parameters?.temperature || 0.7,
            updateFn: (value) => {
                if (!character.ai_parameters) character.ai_parameters = {};
                character.ai_parameters.temperature = value;
            }
        },
        'top-p': {
            value: character.ai_parameters?.top_p || 0.9,
            updateFn: (value) => {
                if (!character.ai_parameters) character.ai_parameters = {};
                character.ai_parameters.top_p = value;
            }
        },
        'presence-penalty': {
            value: character.ai_parameters?.presence_penalty || 0.6,
            updateFn: (value) => {
                if (!character.ai_parameters) character.ai_parameters = {};
                character.ai_parameters.presence_penalty = value;
            }
        },
        'frequency-penalty': {
            value: character.ai_parameters?.frequency_penalty || 0.6,
            updateFn: (value) => {
                if (!character.ai_parameters) character.ai_parameters = {};
                character.ai_parameters.frequency_penalty = value;
            }
        }
    };

    // Initialize each parameter control
    Object.entries(parameterControls).forEach(([id, config]) => {
        const input = document.getElementById(id);
        if (input) {
            input.value = config.value;
            const valueDisplay = input.nextElementSibling;
            if (valueDisplay) {
                valueDisplay.textContent = config.value.toFixed(1);
            }
            setupParameterListener(input, config.updateFn);
        }
    });
}

function setupParameterListener(input, updateFn) {
    input.addEventListener('input', (e) => {
        const value = parseFloat(e.target.value);
        const valueDisplay = input.nextElementSibling;
        
        if (valueDisplay) {
            valueDisplay.textContent = value.toFixed(1);
        }

        // Update only the session parameters
        updateFn(value);
    });
}


// Function to get current credit cost
function getCreditCost() {
    return audioEnabled ? 15 : 10;
}

// Chat state
let chatHistory = [];
const MAX_HISTORY_LENGTH = 10;
let messageQueue = [];
const MAX_QUEUE_SIZE = 5;
let isProcessing = false;

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
    console.log("Sending initial greeting...");
    
    // Get random greeting or use default
    let characterGreeting = "Hello! How can I help you today?";
    if (character.greetings && Array.isArray(character.greetings) && character.greetings.length > 0) {
        characterGreeting = character.greetings[Math.floor(Math.random() * character.greetings.length)];
    }

    // Add system prompt and greeting to chat history
    const systemMessage = {
        role: "system",
        content: character.systemPrompt
    };
    
    const assistantMessage = {
        role: "assistant",
        content: characterGreeting
    };
    
    chatHistory.push(systemMessage, assistantMessage);
    
    // Add greeting to chat display
    addMessage("bot", characterGreeting);

    // Clear existing queue and add greeting for TTS
    if (audioEnabled) {
        const ttsText = filterTextForTTS(characterGreeting);
        if (ttsText) {
            console.log("Adding greeting to message queue:", ttsText);
            messageQueue = [ttsText];
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
function updateCreditDisplay() {
    // Try both credit display locations
    const headerText = document.querySelector('.header-text');
    const creditsDisplay = document.querySelector('.credit-display');
    let creditDisplay;

    if (creditsDisplay) {
        creditDisplay = creditsDisplay;
    } else if (headerText) {
        creditDisplay = document.createElement('div');
        creditDisplay.className = 'credit-display';
        headerText.appendChild(creditDisplay);
    }

    if (creditDisplay && currentUser) {
        creditDisplay.innerHTML = `Credits: ${currentUser.user.credits}`;
        console.log(`Updated credit display: ${currentUser.user.credits}`);
    }
}

async function sendMessage(userMessage = null) {
    if (isProcessing) {
        console.log("Already processing a message, please wait...");
        return;
    }

    const creditCost = getCreditCost();

    // Check credits before proceeding
    if (currentUser && currentUser.user.credits < creditCost) {
        addMessage("bot", "Insufficient credits. Please purchase more credits to continue chatting.");
        return;
    }

    try {
        const message = userMessage || userInput.value.trim();
        if (!message) return;

        // Stop current audio when sending new message
        stopCurrentAudio();

        isProcessing = true;
        if (!userMessage) {
            addMessage("user", message);
            userInput.value = "";
        }
        
        userInput.disabled = true;
        sendButton.disabled = true;

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
                temperature: sessionParameters.ai.temperature,
                max_tokens: character.ai_parameters?.max_tokens || 150,
                top_p: sessionParameters.ai.topP,
                presence_penalty: sessionParameters.ai.presencePenalty,
                frequency_penalty: sessionParameters.ai.frequencyPenalty
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

        // Update credits after successful message
        if (currentUser) {
            currentUser.user.credits -= creditCost;
            updateCreditDisplay();
            
            // Log credit usage
            console.log(`Credits used: ${creditCost}. Remaining credits: ${currentUser.user.credits}`);
        }

        if (audioEnabled) {
            const ttsText = filterTextForTTS(botMessage);
            if (ttsText) {
                messageQueue.push(ttsText);
                if (!isAudioPlaying) {
                    processNextInQueue();
                }
            }
        }

    } catch (error) {
        console.error("Error details:", error);
        addMessage("bot", "I apologize, there was an error. Your credits have been refunded.");
        
        // Refund credits if there was an error
        if (currentUser) {
            currentUser.user.credits += creditCost;
            updateCreditDisplay();
            console.log(`Credits refunded: ${creditCost}. Current credits: ${currentUser.user.credits}`);
        }
    } finally {
        isProcessing = false;
        userInput.disabled = false;
        sendButton.disabled = false;
        userInput.focus();
    }
}

async function processNextInQueue() {
    if (messageQueue.length === 0) {
        console.log("Message queue empty");
        return;
    }

    if (isAudioPlaying) {
        console.log("Audio currently playing, waiting...");
        return;
    }

    try {
        const text = messageQueue[0];
        console.log("Processing TTS for text:", text);
        
        // Get the actual voice model to use - either the character's own or an existing one
        const voiceModel = character.existingCharacterModel || character.rvc_model || character.id;
        
        const requestBody = {
            text: text,
            edge_voice: character.ttsVoice,
            rvc_model: voiceModel,  // Use the correct voice model
            tts_rate: sessionParameters.voice.ttsRate,
            rvc_pitch: sessionParameters.voice.rvcPitch
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
        
        if (!ttsData.audio_url) {
            throw new Error("No audio URL received from TTS service");
        }

        await playAudio(ttsData.audio_url);

    } catch (error) {
        console.error("TTS error:", error);
        messageQueue.shift(); // Remove failed message from queue
        isAudioPlaying = false;
        if (messageQueue.length > 0) {
            setTimeout(processNextInQueue, 100);
        }
    }
}
async function playAudio(audioUrl) {
    if (!audioEnabled) return;

    try {
        // Stop any currently playing audio
        if (currentAudioPlayer) {
            currentAudioPlayer.pause();
            currentAudioPlayer.src = '';
            currentAudioPlayer = null;
        }

        isAudioPlaying = true;
        const audioPlayer = new Audio(audioUrl);
        currentAudioPlayer = audioPlayer;

        // Set up event listeners
        audioPlayer.addEventListener('ended', () => {
            isAudioPlaying = false;
            currentAudioPlayer = null;
            messageQueue.shift(); // Remove played message from queue
            if (messageQueue.length > 0) {
                setTimeout(processNextInQueue, 100);
            }
        });

        audioPlayer.addEventListener('error', (e) => {
            console.error("Audio playback error:", e);
            isAudioPlaying = false;
            currentAudioPlayer = null;
            messageQueue.shift(); // Remove failed message from queue
            if (messageQueue.length > 0) {
                setTimeout(processNextInQueue, 100);
            }
        });

        // Add abort handler
        audioPlayer.addEventListener('abort', () => {
            isAudioPlaying = false;
            currentAudioPlayer = null;
            if (messageQueue.length > 0) {
                setTimeout(processNextInQueue, 100);
            }
        });

        await audioPlayer.play();

    } catch (error) {
        console.error("Error in playAudio:", error);
        isAudioPlaying = false;
        currentAudioPlayer = null;
        messageQueue.shift(); // Remove failed message from queue
        if (messageQueue.length > 0) {
            setTimeout(processNextInQueue, 100);
        }
    }
}

// Add a function to stop current audio
function stopCurrentAudio() {
    if (currentAudioPlayer) {
        currentAudioPlayer.pause();
        currentAudioPlayer.src = '';
        currentAudioPlayer = null;
    }
    isAudioPlaying = false;
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

        
        // Initialize parameters
        initializeParameters();

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
    chatInput.style.display = 'none';
    startChatButton.addEventListener('click', async () => {
        console.log("Start chat clicked, message queue:", messageQueue);
        startChatOverlay.style.display = 'none';
        chatInput.style.display = 'flex';
        userInput.focus();
        
        // Clear any existing queue and audio
        if (currentAudioPlayer) {
            currentAudioPlayer.pause();
            currentAudioPlayer = null;
        }
        messageQueue = [];
        
        // Send new greeting
        await sendInitialGreeting();
        
        // Process greeting audio if enabled
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
        if (clearButton){
            clearButton.onclick = clearChatState;
        }

        // Initialize greeting

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
        
        // Update nav panel login state
        const loggedOutView = document.getElementById('logged-out-view');
        const loggedInView = document.getElementById('logged-in-view');
        const usernameDisplay = document.getElementById('username-display');
        const creditsDisplay = document.getElementById('credits-display');
        
        if (currentUser) {
            loggedOutView.style.display = 'none';
            loggedInView.style.display = 'block';
            usernameDisplay.textContent = currentUser.user.username;
            creditsDisplay.textContent = `Credits: ${currentUser.user.credits}`;
        } else {
            loggedOutView.style.display = 'block';
            loggedInView.style.display = 'none';
        }
        
        return true;
    } catch (error) {
        console.error('Auth check failed:', error);
        window.location.href = '/login.html';
        return false;
    }
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

        // Set up audio toggle
        const audioToggle = document.querySelector('.audio-toggle');
        if (audioToggle) {
            audioToggle.onclick = toggleAudio;
            audioToggle.title = `Credits per message: ${audioEnabled ? "15" : "10"}`;
        }
    } catch (error) {
        console.error('Error initializing chat:', error);
        showInitializationError(error);
    }
});

// Audio state
let audioEnabled = true;
let autoplayEnabled = true;
let currentAudioPlayer = null;
let currentAudioUrl = null;


// Configuration and state management
let currentUser = null;
const character = JSON.parse(sessionStorage.getItem("selectedCharacter"));
const chatLog = document.getElementById("chat-log");
const userInput = document.getElementById("user-input");
const sendButton = document.getElementById("send-button");

// New parameter state management
let currentParameters = {
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
    const debouncedSave = debounce(saveParameters, 1000);

    input.addEventListener('input', (e) => {
        const value = parseFloat(e.target.value);
        const valueDisplay = input.nextElementSibling;
        
        if (valueDisplay) {
            valueDisplay.textContent = value.toFixed(1);
        }

        // Update the character object
        updateFn(value);

        // Save changes
        debouncedSave();
    });
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

async function saveParameters() {
    try {
        const response = await fetch(`/characters/${character.id}/update`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                rvc_pitch: character.rvc_pitch,
                tts_rate: character.tts_rate,
                ai_parameters: character.ai_parameters
            })
        });

        if (!response.ok) {
            throw new Error('Failed to save parameters');
        }

        console.log('Parameters saved successfully');
    } catch (error) {
        console.error('Error saving parameters:', error);
    }
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
                if (messageQueue.length === 1) {
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
    if (messageQueue.length === 0 || isAudioPlaying) {
        console.log("Queue empty or audio playing");
        return;
    }

    try {
        const text = messageQueue[0];
        console.log("Processing TTS for text:", text);
        
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
        
        if (!ttsData.audio_url) {
            throw new Error("No audio URL received from TTS service");
        }

        await playAudio(ttsData.audio_url);

    } catch (error) {
        console.error("TTS error:", error);
    } finally {
        messageQueue.shift();
        if (messageQueue.length > 0 && !isAudioPlaying) {
            setTimeout(() => processNextInQueue(), 100); // Small delay between messages
        }
    }
}

let isAudioPlaying = false;

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

        isAudioPlaying = true;
        const audioPlayer = new Audio(audioUrl);
        currentAudioPlayer = audioPlayer;
        currentAudioUrl = audioUrl;

        audioPlayer.addEventListener('ended', () => {
            isAudioPlaying = false;
            currentAudioUrl = null;
            currentAudioPlayer = null;
        });

        audioPlayer.addEventListener('error', (e) => {
            console.error("Audio playback error:", e);
            isAudioPlaying = false;
            currentAudioPlayer = null;
            currentAudioUrl = null;
        });

        await audioPlayer.play();

    } catch (error) {
        console.error("Error in playAudio:", error);
        isAudioPlaying = false;
        currentAudioPlayer = null;
        currentAudioUrl = null;
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

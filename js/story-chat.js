import { currentUser, checkAuth, openAuthModal } from '../auth.js';
import { generateCharacterImage, updatePanelBackground, animateTransition } from './imageGenerator.js';

// State management
let characters = [], messages = [], isProcessing = false, audioEnabled = true;
let currentAudioPlayer = null;
let storySessionId = null;
let storybookModeActive = false; // Add this line for storybook mode state
const sessionId = window.location.pathname.split('/').pop();

// Endless mode state
let endlessModeActive = false;
let endlessModeSettings = {
    delay: 5,
    maxTurns: 50,
    temperature: 0.8
};
let currentTurn = 0;
let endlessModeTimeout = null;

document.addEventListener('DOMContentLoaded', async () => {
    if (!await checkAuth()) {
        openAuthModal('login');
        return;
    }
    
    await Promise.all([
        loadSession(),
        initializeKoboldSession(),
        setupImageGallery()
    ]);
    
    setupEventListeners();
    setupEndlessMode();
    setupStorybookMode();
});

function setupImageGallery() {
    // Add image gallery container above chat panels
    const galleryHTML = `
        <div id="storybook-gallery" class="storybook-gallery">
            <div class="gallery-thumbnails"></div>
            <div id="image-modal" class="image-modal">
                <span class="close-modal">&times;</span>
                <img class="modal-content" id="modal-image">
            </div>
        </div>
    `;
    
    const panelsGrid = document.getElementById('panels-grid');
    panelsGrid.insertAdjacentHTML('beforebegin', galleryHTML);

    // Set up modal functionality
    const modal = document.getElementById('image-modal');
    const closeBtn = modal.querySelector('.close-modal');
    closeBtn.onclick = () => modal.style.display = 'none';
}

function addImageToGallery(imageData, character) {
    const gallery = document.querySelector('.gallery-thumbnails');
    const thumbnail = document.createElement('div');
    thumbnail.className = 'gallery-thumbnail';
    thumbnail.innerHTML = `
        <img src="data:image/png;base64,${imageData}" 
             alt="${character.name}'s scene" 
             title="${character.name}'s scene">
        <span class="thumbnail-label">${character.name}</span>
    `;

    // Add click handler for full-size view
    thumbnail.onclick = () => {
        const modal = document.getElementById('image-modal');
        const modalImg = document.getElementById('modal-image');
        modal.style.display = 'block';
        modalImg.src = `data:image/png;base64,${imageData}`;
    };

    gallery.appendChild(thumbnail);
}


async function initializeKoboldSession() {
    try {
        // Change to use the correct multiplayer endpoint
        const response = await fetch('/api/extra/multiplayer/getstory', {
            method: 'POST',  // Changed from GET to POST
            headers: { 'accept': 'text/plain' },  // Changed content-type to match working curl
            credentials: 'include'
        });
        
        if (!response.ok) throw new Error('Failed to create KoboldCPP session');
        // No need to parse as JSON since it returns raw text
        storySessionId = Date.now().toString(); 
        await updateKoboldContext();
    } catch (error) {
        console.error('Error initializing KoboldCPP session:', error);
    }
}

async function updateKoboldContext() {
    if (!storySessionId) return;
    try {
        const storyResponse = await fetch(`/story/sessions/${sessionId}`);
        const storyData = await storyResponse.json();
        
        const storyUpdate = {
            full_update: true,
            sender: `USER_${sessionId}`,
            data_format: "kcpp_lzma_b64",  // Changed to match KoboldCPP format
            data: {
                scenario: storyData.scenario,
                messages: messages,
                characters: storyData.characters
            }
        };

        // Use the correct multiplayer endpoint
        const response = await fetch('/api/extra/multiplayer/setstory', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify(storyUpdate)
        });
        if (!response.ok) throw new Error('Failed to update context');
    } catch (error) {
        console.error('Error updating KoboldContext:', error);
    }
}



async function generateCharacterPrompt(character, message, recentContext) {
    try {
        const promptContext = `
Character: ${character.name}
Description: ${character.description || 'No description available'}
Current message: ${message}
Recent context: ${recentContext}

Create a visual description focusing on ${character.name} as the main subject, incorporating their current action or state, and the scene setting. Description:`;

        const response = await fetch('/api/v1/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                prompt: promptContext,
                max_new_tokens: 150,
                temperature: 0.7,
                stop_sequence: ["\n", "."]
            })
        })
        
        if (!response.ok) throw new Error('Failed to generate image prompt');
        const data = await response.json();
        
        let prompt = data.results[0].text.trim();
        return `${prompt}, character portrait, ${character.name}, cinematic lighting, detailed features, expressive pose, high quality, masterpiece, best quality, highly detailed, dramatic`;
    } catch (error) {
        console.error('Error generating prompt:', error);
        return `portrait of ${character.name}, ${message.slice(0, 100)}, cinematic lighting, high quality, masterpiece`;
    }
}
// Session loading and UI setup
async function loadSession() {
    try {
        const response = await fetch(`/story/sessions/${sessionId}`, {
            credentials: 'include'
        });
        if (!response.ok) throw new Error('Failed to load session');

        const data = await response.json();
        characters = data.characters;

        const charactersByPosition = new Array(4).fill(null);
        characters.forEach(char => {
            if (char.position >= 0 && char.position < 4) {
                charactersByPosition[char.position] = char;
            }
        });

        const panelsGrid = document.getElementById('panels-grid');
        if (!panelsGrid) return;

        panelsGrid.innerHTML = charactersByPosition.map((char, index) => {
            const character = char || {
                id: `empty-${index}`,
                name: 'Loading...',
                avatar: 'default-bg.jpg',
                position: index
            };

            return `
                <div class="chat-panel" data-position="${index}" data-character-id="${character.id}">
                    <div class="panel-background" style="background-image: url('../${character.background || 'default-bg.jpg'}')"></div>
                    <div class="panel-header">
                        <img src="../${character.avatar}" alt="${character.name}" class="panel-avatar" 
                             onerror="this.src='../avatars/default-user.png'">
                        <span class="panel-name">${character.name}</span>
                    </div>
                    <div class="chat-messages" id="chat-messages-${index}"></div>
                </div>
            `;
        }).join('');

    } catch (error) {
        console.error('Error loading session:', error);
    }
}

// Message handling
function addMessage(message) {
    messages.push(message);
    const container = message.type === 'user' ? 
        document.getElementById('user-chat-messages') : 
        document.getElementById(`chat-messages-${message.position}`);

    if (!container) return;

    const messageHTML = `
        <div class="message-container ${message.type}">
            <div class="message-bubble">${message.content}</div>
        </div>
    `;
    
    container.insertAdjacentHTML('beforeend', messageHTML);
    container.scrollTop = container.scrollHeight;

    if (message.type !== 'user') {
        const msgs = container.querySelectorAll('.message-container');
        if (msgs.length > 10) msgs[0].remove();
    }

    localStorage.setItem(`story_${sessionId}_messages`, JSON.stringify(messages));
}

async function processMessage(message, temperature = 0.7) {
    try {
        await updateKoboldContext();
        const response = await fetch('/v1/story/completions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                session_id: sessionId,
                message: message,
                messages: messages.map(msg => ({
                    role: msg.type === 'user' ? 'user' : 'assistant',
                    content: msg.content
                })),
                temperature: temperature,
                // Add these parameters to get better responses
                max_tokens: 500,        // Allow longer responses
                top_p: 0.9,            // More focused responses
                frequency_penalty: 0.7, // Encourage variety
                presence_penalty: 0.7,  // Encourage context usage
                // Only use stop sequences that make sense
                stop_sequences: ["\n\n"]  // Remove User: and Character: from stop sequences
            })
        });
        if (!response.ok) {
            if (response.status === 402) throw new Error('Insufficient credits');
            throw new Error('Failed to get responses');
        }

        const data = await response.json();
        const parsedResponses = parseCharacterResponses(data);
        
        for (const response of parsedResponses) {
            addMessage(response);

        if (storybookModeActive) {
            const character = characters.find(c => c.id === response.character_id);
            if (character) {
                const recentContext = messages.slice(-3).map(msg => 
                    `${msg.type === 'user' ? 'User' : msg.name}: ${msg.content}`
                ).join('\n');
        
                // Show loading state in gallery
                const removeLoading = showLoadingThumbnail(character);
                
                const imageData = await generateCharacterImage(character, response.content, recentContext);
                if (imageData) {
                    addImageToGallery(imageData, character);
                }
        
                // Remove loading state
                removeLoading();
            }
        }
            if (audioEnabled) {
                await playAudio(response);
            }
        }
    } catch (error) {
        console.error('Error in processMessage:', error);
        throw error;
    }
}

// Add this function to setup the storybook toggle
function setupStorybookMode() {
    const storybookToggle = document.getElementById('storybook-toggle');
    if (!storybookToggle) return;

    storybookToggle.addEventListener('click', () => {
        storybookModeActive = !storybookModeActive;
        document.body.classList.toggle('storybook-mode', storybookModeActive);
        storybookToggle.classList.toggle('active', storybookModeActive);
        
        // If turning on storybook mode, regenerate images for recent messages
        if (storybookModeActive) {
            regenerateRecentImages();
        }
    });
}

function showLoadingThumbnail(character) {
    const gallery = document.querySelector('.gallery-thumbnails');
    const loadingThumbnail = document.createElement('div');
    loadingThumbnail.className = 'gallery-thumbnail loading';
    loadingThumbnail.innerHTML = `
        <div class="loading-spinner"></div>
        <span class="thumbnail-label">${character.name}</span>
    `;
    gallery.appendChild(loadingThumbnail);

    // Return a function to remove this loading thumbnail
    return () => loadingThumbnail.remove();
}

async function regenerateRecentImages() {
    const recentMessages = messages.slice(-4).filter(msg => msg.type === 'character');
    
    for (const message of recentMessages) {
        const character = characters.find(c => c.id === message.character_id);
        if (!character) continue;

        const recentContext = messages
            .slice(-3)
            .map(msg => `${msg.type === 'user' ? 'User' : msg.name}: ${msg.content}`)
            .join('\n');

        // Show loading state
        const removeLoading = showLoadingThumbnail(character);

        const imageData = await generateCharacterImage(character, message.content, recentContext);
        if (imageData) {
            addImageToGallery(imageData, character);
        }

        // Remove loading thumbnail
        removeLoading();
    }
}

function cleanUserMessage(message) {
    message = message.replace(/^[A-Z]\)\s*/, '')
        .replace(/^"(.+)"$/, '$1');
    
    if (characters && characters.length > 0) {
        characters.forEach(char => {
            if (char.name) {
                const regex = new RegExp(`^${char.name}:\\s*.+$/gm`, 'i');
                message = message.replace(regex, '');
            }
        });
    }
    
    return message.replace(/^[A-Z][a-z]+:\s*.+$/gm, '')
        .replace(/### User's Choice:.+/gs, '')
        .replace(/Choose the response.+/gs, '')
        .replace(/### End of response ##/g, '')
        .replace(/```/g, '')
        .replace(/\*\*/g, '')
        .replace(/Input:.*?Output:/gs, '')
        .replace(/# Story continues.*/s, '')
        .replace(/python\s*$/g, '')
        .replace(/^\s*$\n/gm, '')
        .trim();
}

function parseCharacterResponses(data) {
    const responses = [];
    if (!data || !Array.isArray(data.responses)) return responses;

    const characterNames = new Set(characters.map(char => char.name));
    
    for (const charResponse of data.responses) {
        if (!charResponse || !charResponse.content) continue;

        let content = charResponse.content;
        
        // Only clean up other character's dialogue, keep the current character's full response
        characterNames.forEach(name => {
            if (name !== charResponse.name) {
                const regex = new RegExp(`${name}:\\s*[^\\n]*\\n?`, 'g');
                content = content.replace(regex, '');
            }
        });

        // Less aggressive cleanup to preserve more of the response
        content = content
            .replace(/User:\s*[^\n]*\n?/g, '')
            .replace(/```/g, '')
            .replace(/###[^#]+###/g, '')
            .replace(/Next:.*/s, '')
            .replace(/Let me know.*/s, '')
            .replace(/Choose the response.*/s, '')
            .replace(/^\s*$\n/gm, '')
            .trim();

        // Make sure asterisk expressions are properly closed
        const asteriskCount = (content.match(/\*/g) || []).length;
        if (asteriskCount % 2 !== 0) {
            if (asteriskCount % 2 === 1) {
                content += '*';
            }
        }

        if (content) {
            responses.push({
                type: 'character',
                character_id: charResponse.character_id,
                content: content,
                position: charResponse.position,
                name: charResponse.name,
                ttsVoice: charResponse.ttsVoice,
                rvc_model: charResponse.rvc_model,
                tts_rate: charResponse.tts_rate,
                rvc_pitch: charResponse.rvc_pitch
            });
        }
    }

    return responses;
}


function setupEndlessMode() {
    // Remove the HTML injection since controls already exist
    setupEndlessModeListeners();
}



function setupEndlessModeListeners() {
    const toggleBtn = document.getElementById('endless-mode-toggle');
    const settingsBtn = document.getElementById('endless-mode-settings');
    const settingsPanel = document.getElementById('endless-mode-settings-panel');
    
    const delayInput = document.getElementById('endless-delay');
    const maxTurnsInput = document.getElementById('endless-max-turns');
    const temperatureInput = document.getElementById('endless-temperature');
    
    toggleBtn.addEventListener('click', () => {
        endlessModeActive = !endlessModeActive;
        toggleBtn.textContent = endlessModeActive ? 'Stop Endless Mode' : 'Start Endless Mode';
        toggleBtn.style.backgroundColor = endlessModeActive ? 'var(--error)' : 'var(--primary)';
        
        if (endlessModeActive) {
            currentTurn = 0;
            startEndlessMode();
            document.getElementById('user-input').disabled = true;
            document.getElementById('send-button').disabled = true;
        } else {
            stopEndlessMode();
            document.getElementById('user-input').disabled = false;
            document.getElementById('send-button').disabled = false;
        }
    });

    settingsBtn.addEventListener('click', () => {
        settingsPanel.style.display = settingsPanel.style.display === 'none' ? 'block' : 'none';
    });

    delayInput.addEventListener('input', (e) => {
        endlessModeSettings.delay = parseFloat(e.target.value);
        document.getElementById('endless-delay-value').textContent = `${e.target.value}s`;
    });

    maxTurnsInput.addEventListener('input', (e) => {
        endlessModeSettings.maxTurns = parseInt(e.target.value);
        document.getElementById('endless-max-turns-value').textContent = `${e.target.value} turns`;
    });

    temperatureInput.addEventListener('input', (e) => {
        endlessModeSettings.temperature = parseFloat(e.target.value);
        document.getElementById('endless-temperature-value').textContent = e.target.value;
    });

    document.addEventListener('click', (e) => {
        if (!settingsPanel.contains(e.target) && e.target !== settingsBtn) {
            settingsPanel.style.display = 'none';
        }
    });
}

async function generateUserMessage() {
    try {
        const response = await fetch('/v1/story/user-message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                session_id: sessionId,
                messages: messages.map(msg => ({
                    role: msg.type === 'user' ? 'user' : 'assistant',
                    content: msg.content
                })),
                temperature: endlessModeSettings.temperature
            })
        });

        if (!response.ok) throw new Error('Failed to generate user message');
        const data = await response.json();
        return cleanUserMessage(data.message);
    } catch (error) {
        console.error('Error generating user message:', error);
        return null;
    }
}

async function startEndlessMode() {
    if (!endlessModeActive || currentTurn >= endlessModeSettings.maxTurns) {
        stopEndlessMode();
        return;
    }

    try {
        const userMessage = await generateUserMessage();
        if (!userMessage) {
            console.error('Failed to generate user message');
            stopEndlessMode();
            return;
        }

        addMessage({ 
            type: 'user', 
            content: userMessage,
            id: `user-msg-${currentTurn}`
        });

        await processMessage(userMessage, endlessModeSettings.temperature);
        
        currentTurn++;
        
        if (endlessModeActive) {
            endlessModeTimeout = setTimeout(
                startEndlessMode, 
                endlessModeSettings.delay * 1000
            );
        }

    } catch (error) {
        console.error('Error in endless mode:', error);
        stopEndlessMode();
    }
}

function stopEndlessMode() {
    endlessModeActive = false;
    if (endlessModeTimeout) {
        clearTimeout(endlessModeTimeout);
        endlessModeTimeout = null;
    }
    currentTurn = 0;
    
    document.getElementById('user-input').disabled = false;
    document.getElementById('send-button').disabled = false;
    
    const toggleBtn = document.getElementById('endless-mode-toggle');
    if (toggleBtn) {
        toggleBtn.textContent = 'Start Endless Mode';
        toggleBtn.style.backgroundColor = 'var(--primary)';
    }
}

// Audio playback
async function playAudio(response) {
    try {
        if (currentAudioPlayer) {
            currentAudioPlayer.pause();
            currentAudioPlayer = null;
        }

        const ttsResponse = await fetch('/v1/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: response.content.replace(/\*[^*]*\*/g, '').trim(),
                edge_voice: response.ttsVoice,
                rvc_model: response.rvc_model || response.character_id,
                tts_rate: response.tts_rate || 0,
                rvc_pitch: response.rvc_pitch || 0
            })
        });

        if (!ttsResponse.ok) throw new Error('TTS generation failed');
        const audioData = await ttsResponse.json();
        
        await new Promise((resolve, reject) => {
            const audio = new Audio(audioData.audio_url);
            currentAudioPlayer = audio;
            audio.onended = resolve;
            audio.onerror = reject;
            audio.play().catch(reject);
        });
    } catch (error) {
        console.error('Audio playback error:', error);
    }
}

// Event listeners setup
function setupEventListeners() {
    const userInput = document.getElementById('user-input');
    const sendButton = document.getElementById('send-button');
    const audioToggle = document.querySelector('.audio-toggle');

    sendButton?.addEventListener('click', sendMessage);
     userInput?.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    audioToggle?.addEventListener('click', () => {
        audioEnabled = !audioEnabled;
        audioToggle.textContent = audioEnabled ? '🔊' : '🔇';
        if (!audioEnabled && currentAudioPlayer) {
            currentAudioPlayer.pause();
            currentAudioPlayer = null;
        }
    });
}

async function sendMessage() {
    if (endlessModeActive || isProcessing) return;
    
    const userInput = document.getElementById('user-input');
    const message = userInput.value.trim();
    
    if (!message) return;

    try {
        isProcessing = true;
        const inputValue = message; // Store the message
        userInput.value = ''; // Clear input immediately
        addMessage({ type: 'user', content: inputValue });
        await processMessage(inputValue);
    } catch (error) {
        console.error('Error:', error);
        // Restore input value on error
        userInput.value = message;
        addMessage({
            type: 'system',
            content: error.message,
            error: true
        });
    } finally {
        isProcessing = false;
        userInput.focus();
    }
}

// Load saved messages from localStorage on initialization
document.addEventListener('DOMContentLoaded', async () => {
    if (!await checkAuth()) {
        openAuthModal('login');
        return;
    }
    
    const savedMessages = localStorage.getItem(`story_${sessionId}_messages`);
    if (savedMessages) {
        const parsedMessages = JSON.parse(savedMessages);
        parsedMessages.forEach(msg => addMessage(msg));
    }
    

});

export {
    loadSession,
    addMessage,
    sendMessage,
    playAudio
};
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

function adjustLayoutSizes() {
    const gallery = document.querySelector('.storybook-gallery');
    const panelsGrid = document.querySelector('.chat-panels-grid');
    const userArea = document.querySelector('.user-chat-area');

    if (!panelsGrid || !userArea) return;

    const galleryHeight = storybookModeActive ? gallery?.offsetHeight || 0 : 0;
    const userAreaHeight = userArea.offsetHeight;

    // Update panels grid height
    panelsGrid.style.height = `calc(100vh - ${galleryHeight + userAreaHeight + 20}px)`;
}

document.addEventListener('DOMContentLoaded', async () => {
    if (!await checkAuth()) {
        openAuthModal('login');
        return;
    }
    
    // Load saved messages first
    const savedMessages = localStorage.getItem(`story_${sessionId}_messages`);
    if (savedMessages) {
        const parsedMessages = JSON.parse(savedMessages);
        parsedMessages.forEach(msg => addMessage(msg));
    }

    // Initialize everything else
    await Promise.all([
        initializeNavigation(),
        loadSession(),
        initializeKoboldSession(),
        setupImageGallery()
    ]);
    
    setupEventListeners();
    setupEndlessMode();
    setupStorybookMode();
    adjustLayoutSizes();

    window.addEventListener('resize', adjustLayoutSizes);
});

function setupImageGallery() {
    const gallery = document.querySelector('.gallery-thumbnails');
    if (!gallery) return;

    // Clear existing thumbnails
    gallery.innerHTML = '';

    // Set up modal functionality
    const modal = document.getElementById('image-modal');
    const closeBtn = modal.querySelector('.close-modal');
    closeBtn.onclick = () => {
        modal.classList.remove('active');
    };

    // Close modal on outside click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('active');
        }
    });

    return gallery;
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
        const modalImg = modal.querySelector('.modal-content');
        modal.classList.add('active');
        modalImg.src = `data:image/png;base64,${imageData}`;
    }

    // Add to start of gallery
    gallery.insertBefore(thumbnail, gallery.firstChild);

    // Scroll to the start to show new image
    gallery.scrollLeft = 0;

    // Optional: Remove older thumbnails if too many (e.g., keep last 20)
    const maxThumbnails = 20;
    const thumbnails = gallery.querySelectorAll('.gallery-thumbnail');
    if (thumbnails.length > maxThumbnails) {
        thumbnails[thumbnails.length - 1].remove();
    }
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

        // Add these lines to ensure proper layout
        panelsGrid.style.marginLeft = 'var(--nav-width)';
        panelsGrid.style.width = 'calc(100% - var(--nav-width))';

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
        
        // Initial response round
        const responses = await generateCharacterResponses(message, temperature);
        if (!responses.length) {
            throw new Error('No valid responses generated');
        }

        // Process initial responses
        for (const response of responses) {
            await processCharacterResponse(response);
        }

        // Generate follow-up interactions (1-2 rounds)
        const followUpRounds = Math.floor(Math.random() * 2) + 1; // 1 or 2 rounds
        let lastSpeakers = new Set(responses.map(r => r.character_id));
        let availableCharacters = characters.filter(c => !lastSpeakers.has(c.id));

        for (let i = 0; i < followUpRounds; i++) {
            if (!availableCharacters.length) break;

            // Choose next speakers based on context
            const nextSpeakers = chooseNextSpeakers(responses[responses.length - 1], availableCharacters);
            if (!nextSpeakers.length) break;

            // Generate and process follow-up responses
            const followUpResponses = await generateFollowUpResponses(nextSpeakers, responses, temperature);
            for (const response of followUpResponses) {
                await processCharacterResponse(response);
                lastSpeakers.add(response.character_id);
            }

            // Update available characters
            availableCharacters = characters.filter(c => !lastSpeakers.has(c.id));
        }

        return responses;
    } catch (error) {
        console.error('Error in processMessage:', error);
        throw error;
    }
}

async function generateCharacterResponses(message, temperature) {
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
            temperature: temperature
        })
    });

    if (!response.ok) {
        if (response.status === 402) {
            throw new Error('Insufficient credits');
        }
        const errorData = await response.json();
        throw new Error(errorData.error || 'Failed to get responses');
    }

    const data = await response.json();
    return parseCharacterResponses(data);
}

async function generateFollowUpResponses(characters, previousResponses, temperature) {
    // Create context from previous responses
    const context = previousResponses.slice(-3).map(r => `${r.name}: ${r.content}`).join('\n');
    
    const response = await fetch('/v1/story/completions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
            session_id: sessionId,
            message: context,
            characters: characters.map(c => c.id),
            messages: messages.map(msg => ({
                role: msg.type === 'user' ? 'user' : 'assistant',
                content: msg.content
            })),
            temperature: temperature
        })
    });

    if (!response.ok) {
        throw new Error('Failed to generate follow-up responses');
    }

    const data = await response.json();
    return parseCharacterResponses(data);
}

async function processCharacterResponse(response) {
    addMessage(response);

    if (storybookModeActive) {
        const character = characters.find(c => c.id === response.character_id);
        if (character) {
            const recentContext = messages.slice(-3).map(msg => 
                `${msg.type === 'user' ? 'User' : msg.name}: ${msg.content}`
            ).join('\n');
    
            const removeLoading = showLoadingThumbnail(character);
            try {
                const imageData = await generateCharacterImage(character, response.content, recentContext);
                if (imageData) {
                    addImageToGallery(imageData, character);
                }
            } catch (error) {
                console.error('Error generating image:', error);
            } finally {
                removeLoading();
            }
        }
    }

    if (audioEnabled) {
        try {
            await playAudio(response);
        } catch (error) {
            console.error('Error playing audio:', error);
        }
    }
}

function chooseNextSpeakers(lastResponse, availableCharacters) {
    const speakers = [];
    
    // Check if any character was mentioned in the last response
    availableCharacters.forEach(char => {
        if (lastResponse.content.toLowerCase().includes(char.name.toLowerCase())) {
            speakers.push(char);
        }
    });

    // If no characters were mentioned, choose 1-2 random characters
    if (!speakers.length && availableCharacters.length) {
        const numSpeakers = Math.min(Math.floor(Math.random() * 2) + 1, availableCharacters.length);
        const shuffled = availableCharacters.sort(() => Math.random() - 0.5);
        speakers.push(...shuffled.slice(0, numSpeakers));
    }

    return speakers;
}

// Add this function to setup the storybook toggle
function setupStorybookMode() {
    const storybookToggle = document.getElementById('storybook-toggle');
    if (!storybookToggle) return;

    storybookToggle.addEventListener('click', () => {
        storybookModeActive = !storybookModeActive;
        document.body.classList.toggle('storybook-mode', storybookModeActive);
        storybookToggle.classList.toggle('active', storybookModeActive);
        
        adjustLayoutSizes();
        
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
    if (!data || !Array.isArray(data.responses)) {
        console.error('Invalid response data format:', data);
        return responses;
    }

    const characterNames = new Set(characters.map(char => char.name));
    
    for (const charResponse of data.responses) {
        if (!charResponse || !charResponse.content || !charResponse.character_id) {
            console.warn('Skipping invalid character response:', charResponse);
            continue;
        }

        let content = charResponse.content;
        
        content = cleanResponseContent(content, characterNames, charResponse.name);

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

function cleanResponseContent(content, characterNames, currentCharName) {
    // Remove other characters' dialogue
    characterNames.forEach(name => {
        if (name !== currentCharName) {
            const regex = new RegExp(`${name}:\\s*[^\\n]*\\n?`, 'g');
            content = content.replace(regex, '');
        }
    });

    // Clean up common artifacts
    content = content
        .replace(/User:\s*[^\n]*\n?/g, '')
        .replace(/```/g, '')
        .replace(/###[^#]+###/g, '')
        .replace(/Next:.*/s, '')
        .replace(/Let me know.*/s, '')
        .replace(/Choose the response.*/s, '')
        .replace(/^\s*$\n/gm, '')
        .trim();

    // Ensure asterisk expressions are properly closed
    const asteriskCount = (content.match(/\*/g) || []).length;
    if (asteriskCount % 2 !== 0) {
        content += '*';
    }

    return content;
}


async function initializeNavigation() {
    const logoLink = document.querySelector('.logo-link');
    if (logoLink) {
        logoLink.addEventListener('click', (e) => {
            e.preventDefault();
            window.location.href = '/';
        });
    }

    const loggedInView = document.getElementById('logged-in-view');
    const loggedOutView = document.getElementById('logged-out-view');
    
    if (currentUser) {
        if (loggedInView && loggedOutView) {
            loggedOutView.style.display = 'none';
            loggedInView.style.display = 'block';
            document.getElementById('username-display').textContent = currentUser.username;
            updateCreditsDisplay();
        }
    }
}

function updateCreditsDisplay() {
    const creditsDisplay = document.getElementById('credits-display');
    if (creditsDisplay && currentUser?.credits !== undefined) {
        creditsDisplay.textContent = `Credits: ${currentUser.credits}`;
    }
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
        toggleBtn.classList.toggle('active');
        toggleBtn.querySelector('.button-icon').textContent = endlessModeActive ? '⏹️' : '🔄';
        
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
        settingsPanel.classList.toggle('active');
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

    // Close settings when clicking outside
    document.addEventListener('click', (e) => {
        if (settingsPanel.classList.contains('active') && 
            !settingsPanel.contains(e.target) && 
            e.target !== settingsBtn) {
            settingsPanel.classList.remove('active');
        }
    });

    // Handle escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && settingsPanel.classList.contains('active')) {
            settingsPanel.classList.remove('active');
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
        toggleBtn.classList.remove('active');
        toggleBtn.querySelector('.button-icon').textContent = '🔄';
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
        audioToggle.classList.toggle('active');
        audioToggle.querySelector('.button-icon').textContent = audioEnabled ? '🔊' : '🔇';
        
        if (!audioEnabled && currentAudioPlayer) {
            currentAudioPlayer.pause();
            currentAudioPlayer = null;
        }
    });

    // Handle settings panel close on outside click
    document.addEventListener('click', (e) => {
        const settingsPanel = document.getElementById('endless-mode-settings-panel');
        const settingsBtn = document.getElementById('endless-mode-settings');
        
        if (settingsPanel?.classList.contains('active') && 
            !settingsPanel.contains(e.target) && 
            e.target !== settingsBtn) {
            settingsPanel.classList.remove('active');
        }
    });

    // Add resize observer for dynamic content
    const resizeObserver = new ResizeObserver(adjustLayoutSizes);
    document.querySelectorAll('.chat-messages').forEach(el => resizeObserver.observe(el));

    // ESC key handler for modals
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            // Close image modal if open
            const imageModal = document.getElementById('image-modal');
            if (imageModal?.classList.contains('active')) {
                imageModal.classList.remove('active');
            }
            // Close settings panel if open
            const settingsPanel = document.getElementById('endless-mode-settings-panel');
            if (settingsPanel?.classList.contains('active')) {
                settingsPanel.classList.remove('active');
            }
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

export {
    loadSession,
    addMessage,
    sendMessage,
    playAudio,
    adjustLayoutSizes,
    processMessage,
    parseCharacterResponses,
    cleanResponseContent,
    generateCharacterResponses,
    generateFollowUpResponses,
    processCharacterResponse,
    chooseNextSpeakers
};
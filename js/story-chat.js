import { currentUser, checkAuth, openAuthModal } from '../auth.js';

let characters = [], messages = [], isProcessing = false, audioEnabled = true, 
    currentAudioPlayer = null, messageQueue = [];
const sessionId = window.location.pathname.split('/').pop();

document.addEventListener('DOMContentLoaded', async () => {
    if (!await checkAuth()) {
        openAuthModal('login');
        return;
    }
    await loadSession();
    setupEventListeners();
});

async function loadSession() {
    try {
        const response = await fetch(`/story/sessions/${sessionId}`, {
            credentials: 'include'
        });
        if (!response.ok) throw new Error('Failed to load session');

        const data = await response.json();
        characters = data.characters;

        console.log('Raw server response:', data);
        console.log('Characters array:', characters.map(c => ({
            id: c.id,
            name: c.name,
            position: c.position
        })));

        const panelsGrid = document.getElementById('panels-grid');
        if (!panelsGrid) return;

        // Ensure we have all characters before building panels
        const charactersByPosition = new Array(4).fill(null);
        characters.forEach(char => {
            if (char.position >= 0 && char.position < 4) {
                charactersByPosition[char.position] = char;
            }
        });

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

function addMessage(message) {
    messages.push(message);

    if (message.type === 'user') {
        const userChat = document.getElementById('user-chat-messages');
        if (!userChat) return;

        const messageHTML = `
            <div class="message-container user">
                <div class="message-bubble">${message.content}</div>
            </div>
        `;
        userChat.insertAdjacentHTML('beforeend', messageHTML);
        userChat.scrollTop = userChat.scrollHeight;
        
        const msgs = userChat.querySelectorAll('.message-container');
        if (msgs.length > 10) msgs[0].remove();
        return;
    }

    if (message.type === 'character') {
        console.log('Processing character message:', {
            position: message.position,
            character_id: message.character_id,
            content_preview: message.content?.substring(0, 50)
        });

        const messagesContainer = document.getElementById(`chat-messages-${message.position}`);
        if (!messagesContainer) {
            console.error('No container found for position:', message.position);
            return;
        }

        const messageHTML = `
            <div class="message-container character">
                <div class="message-bubble">${message.content}</div>
            </div>
        `;
        messagesContainer.insertAdjacentHTML('beforeend', messageHTML);
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }
}

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
    const userInput = document.getElementById('user-input');
    const message = userInput.value.trim();
    
    if (!message || isProcessing) return;

    try {
        isProcessing = true;
        userInput.value = '';
        addMessage({ type: 'user', content: message });

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
                }))
            })
        });

        if (!response.ok) {
            throw new Error(response.status === 402 ? 'Insufficient credits' : 'Failed to get character responses');
        }

        const data = await response.json();
        for (const charResponse of data.responses) {
            if (!charResponse.is_placeholder) {
                addMessage({
                    type: 'character',
                    character_id: charResponse.character_id,
                    content: charResponse.content,
                    position: charResponse.position,
                    name: charResponse.name
                });

                if (audioEnabled) {
                    messageQueue.push({
                        text: charResponse.content,
                        voice: charResponse.ttsVoice,
                        model: charResponse.rvc_model,
                        rate: charResponse.tts_rate,
                        pitch: charResponse.rvc_pitch,
                        character_id: charResponse.character_id
                    });
                }
            }
        }

        if (audioEnabled && messageQueue.length > 0) {
            await processAudioQueue();
        }

    } catch (error) {
        console.error('Error:', error);
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

async function processAudioQueue() {
    while (messageQueue.length > 0) {
        const message = messageQueue[0];
        
        try {
            if (currentAudioPlayer) {
                currentAudioPlayer.pause();
                currentAudioPlayer = null;
            }

            const ttsResponse = await fetch('/v1/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text: message.text.replace(/\*[^*]*\*/g, '').trim(),
                    edge_voice: message.voice,
                    rvc_model: message.model || message.character_id,
                    tts_rate: message.rate || 0,
                    rvc_pitch: message.pitch || 0
                })
            });

            if (!ttsResponse.ok) throw new Error('TTS generation failed');

            const audioData = await ttsResponse.json();
            const audio = new Audio(audioData.audio_url);
            currentAudioPlayer = audio;
            
            await new Promise((resolve, reject) => {
                audio.onended = resolve;
                audio.onerror = reject;
                audio.play().catch(reject);
            });

        } catch (error) {
            console.error('Audio generation error:', error);
        }
        
        messageQueue.shift();
    }
}

window.sendMessage = sendMessage;
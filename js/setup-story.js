import { currentUser, checkAuth, openAuthModal } from '../auth.js';

// State management
let characters = [];
let selectedCharacters = new Map(); // position -> character data

// Initialize setup interface
document.addEventListener('DOMContentLoaded', async () => {
    if (!await checkAuth()) {
        openAuthModal('login');
        return;
    }

    await loadCharacters();
    setupDragAndDrop();
    document.getElementById('create-story')?.addEventListener('click', validateAndCreateStory);
});

async function loadCharacters() {
    try {
        const response = await fetch('/characters/my-library', {
            credentials: 'include'
        });
        
        if (!response.ok) throw new Error('Failed to load characters');
        
        const data = await response.json();
        
        // Combine public and private characters
        characters = [
            ...(data.public || []),
            ...(data.private || [])
        ].filter(char => char.isApproved || char.isPrivate);

        const characterList = document.getElementById('character-list');
        if (!characterList) return;
        
        characterList.innerHTML = characters.map(char => `
            <div class="character-card" draggable="true" data-character-id="${char.id}">
                <img src="../${char.avatar}" alt="${char.name}" 
                     onerror="this.src='../avatars/default-user.png'">
                <div class="character-info">
                    <div class="character-name">${char.name}</div>
                    ${char.isPrivate ? '<span class="private-badge">Private</span>' : ''}
                </div>
            </div>
        `).join('');
    } catch (error) {
        console.error('Error loading characters:', error);
        showError('Failed to load characters. Please try again.');
    }
}

function setupDragAndDrop() {
    const cards = document.querySelectorAll('.character-card');
    const panels = document.querySelectorAll('.setup-panel');

    cards.forEach(card => {
        card.addEventListener('dragstart', (e) => {
            e.dataTransfer.setData('text/plain', card.dataset.characterId);
            card.classList.add('dragging');
        });

        card.addEventListener('dragend', () => {
            card.classList.remove('dragging');
        });
    });

    panels.forEach(panel => {
        panel.addEventListener('dragover', (e) => {
            e.preventDefault();
            if (!panel.classList.contains('occupied')) {
                panel.classList.add('dragover');
            }
        });

        panel.addEventListener('dragleave', () => {
            panel.classList.remove('dragover');
        });

        panel.addEventListener('drop', (e) => {
            e.preventDefault();
            panel.classList.remove('dragover');
            
            const characterId = e.dataTransfer.getData('text/plain');
            const position = panel.dataset.position;

            // Check if panel is already occupied
            if (selectedCharacters.has(position)) {
                return;
            }

            selectedCharacters.set(position, characterId);
            updatePanelDisplay(panel, characterId);
        });
    });
}

function updatePanelDisplay(panel, characterId) {
    const character = characters.find(char => char.id === characterId);
    if (!character) return;

    const bgPath = character.background ? `../${character.background}` : '';
    
    panel.classList.add('occupied');
    panel.innerHTML = `
        <div class="panel-content">
            ${bgPath ? `<div class="panel-background" style="background-image: url('${bgPath}')"></div>` : ''}
            <img src="../${character.avatar}" alt="${character.name}" 
                 class="panel-character-image"
                 onerror="this.src='../avatars/default-user.png'">
            <div class="panel-character-name">${character.name}</div>
            <button class="remove-character" onclick="removeCharacter(event, '${panel.dataset.position}')">
                ✕
            </button>
        </div>
    `;
}

function removeCharacter(event, position) {
    event.stopPropagation();
    const panel = document.querySelector(`.setup-panel[data-position="${position}"]`);
    if (!panel) return;

    selectedCharacters.delete(position);
    panel.classList.remove('occupied');
    panel.innerHTML = '<div class="panel-placeholder">Drop Character Here</div>';
}

function validateAndCreateStory() {
    const title = document.getElementById('story-title')?.value?.trim();
    const scenario = document.getElementById('story-scenario')?.value?.trim();
    
    if (!title) {
        showError('Please enter a story title');
        return;
    }
    
    if (!scenario) {
        showError('Please enter a scenario');
        return;
    }
    
    const activeCharacters = Array.from(selectedCharacters.values()).filter(Boolean);
    if (activeCharacters.length < 2) {
        showError('Please select at least two characters');
        return;
    }

    createStory(title, scenario);
}

async function createStory(title, scenario) {
    try {
        // Create character array with placeholders for empty panels
        const characterData = Array.from({ length: 4 }, (_, i) => ({
            id: selectedCharacters.get(i.toString()) || null,
            position: i,
            is_placeholder: !selectedCharacters.get(i.toString())
        }));

        const response = await fetch('/story/setup', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                title,
                scenario,
                characters: characterData
            })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.message || 'Failed to create story');
        }

        const data = await response.json();
        window.location.href = `/story/${data.session_id}`;
    } catch (error) {
        console.error('Error creating story:', error);
        showError('Failed to create story. Please try again.');
    }
}

function showError(message) {
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error-message';
    errorDiv.textContent = message;
    
    // Remove any existing error messages
    document.querySelectorAll('.error-message').forEach(el => el.remove());
    
    // Insert error message after the create button
    const createButton = document.getElementById('create-story');
    if (createButton) {
        createButton.parentNode.insertBefore(errorDiv, createButton.nextSibling);
        setTimeout(() => errorDiv.remove(), 5000);
    }
}

// Make removeCharacter available globally for the onclick handler
window.removeCharacter = removeCharacter;
import { currentUser } from './auth.js';

const characterModal = document.getElementById('character-modal');
const characterForm = document.getElementById('character-form');

// Modal controls
function openCharacterModal() {
    if (!currentUser) {
        openAuthModal();
        return;
    }
    setupImagePreviews();
    characterModal.showModal();
}

function closeCharacterModal() {
    characterModal.close();
    characterForm.reset();
    document.getElementById('avatar-preview').innerHTML = '';
    document.getElementById('background-preview').innerHTML = '';
}

// Image preview handling
function setupImagePreviews() {
    const avatarInput = document.getElementById('avatar');
    const backgroundInput = document.getElementById('background');
    
    if (avatarInput) {
        setupImagePreview(avatarInput, document.getElementById('avatar-preview'));
    }
    if (backgroundInput) {
        setupImagePreview(backgroundInput, document.getElementById('background-preview'));
    }
}

function setupImagePreview(input, previewElement) {
    if (!input || !previewElement) return;
    
    input.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (e) => {
                const img = document.createElement('img');
                img.src = e.target.result;
                previewElement.innerHTML = '';
                previewElement.appendChild(img);
            };
            reader.readAsDataURL(file);
        }
    });
}

// Handle character creation
characterForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    try {
        // First upload images
        const avatarFile = document.getElementById('avatar').files[0];
        const backgroundFile = document.getElementById('background')?.files[0];
        
        // Upload avatar
        const avatarFormData = new FormData();
        avatarFormData.append('avatar', avatarFile);
        const avatarResponse = await fetch('/upload/avatar', {
            method: 'POST',
            credentials: 'include',
            body: avatarFormData
        });
        
        if (!avatarResponse.ok) {
            throw new Error('Failed to upload avatar');
        }
        
        const { avatarPath } = await avatarResponse.json();
        let backgroundPath = null;
        
        // Upload background if provided
        if (backgroundFile) {
            const backgroundFormData = new FormData();
            backgroundFormData.append('background', backgroundFile);
            const backgroundResponse = await fetch('/upload/character-background', {
                method: 'POST',
                credentials: 'include',
                body: backgroundFormData
            });
            
            if (backgroundResponse.ok) {
                const data = await backgroundResponse.json();
                backgroundPath = data.backgroundPath;
            }
        }
        
        // Create character data
        const formData = new FormData(characterForm);
        const character = {
            name: formData.get('name'),
            description: formData.get('description'),
            systemPrompt: formData.get('systemPrompt'),
            avatar: avatarPath,
            background: backgroundPath,
            ttsVoice: formData.get('ttsVoice'),
            category: formData.get('category'),
            is_private: formData.get('is_private') === 'on',
            tts_rate: parseInt(formData.get('tts_rate')) || 0,
            rvc_pitch: parseInt(formData.get('rvc_pitch')) || 0,
            tags: formData.get('tags')?.split(',').map(tag => tag.trim()).filter(tag => tag) || []
        };
        
        const response = await fetch('/characters/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify(character)
        });
        
        if (!response.ok) {
            throw new Error('Failed to create character');
        }
        
        const { character_id } = await response.json();
        
        // Submit for review if needed
        if (!character.is_private && formData.get('submit_for_review') === 'on') {
            await fetch(`/characters/submit-for-review/${character_id}`, {
                method: 'POST',
                credentials: 'include'
            });
        }
        
        closeCharacterModal();
        window.location.reload(); // Reload to show new character
        
    } catch (error) {
        console.error('Error creating character:', error);
        alert('Failed to create character. Please try again.');
    }
});

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
    const createCharacterBtn = document.getElementById('create-character');
    const closeModalBtns = document.querySelectorAll('.modal-close');
    
    createCharacterBtn?.addEventListener('click', openCharacterModal);
    closeModalBtns.forEach(btn => {
        btn?.addEventListener('click', closeCharacterModal);
    });
});

export {
    openCharacterModal,
    closeCharacterModal
};
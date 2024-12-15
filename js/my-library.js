// State management for editing
let currentCharacter = null;

// character deletion

async function deleteCharacter(characterId) {
    if (!confirm('Are you sure you want to delete this character? This action cannot be undone.')) {
        return;
    }

    try {
        const response = await fetch(`/characters/${characterId}/delete`, {
            method: 'POST',  // Using POST as primary method
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        if (response.status === 405) {  // If POST not allowed, try DELETE
            const deleteResponse = await fetch(`/characters/${characterId}/delete`, {
                method: 'DELETE',
                credentials: 'include'
            });
            if (!deleteResponse.ok) {
                const error = await deleteResponse.json();
                throw new Error(error.error || 'Failed to delete character');
            }
            response = deleteResponse;
        }

        const result = await response.json();
        
        if (response.status === 207) {  // Partial success
            console.warn('Character deleted with some errors:', result.errors);
            alert('Character was deleted but some files may remain: ' + result.errors.join('\n'));
        }

        // Remove the character card from the DOM
        const characterCard = document.querySelector(`[data-character-id="${characterId}"]`);
        if (characterCard) {
            characterCard.remove();
        }

        // Refresh the character lists
        await loadCharacters();

    } catch (error) {
        console.error('Error deleting character:', error);
        alert('Failed to delete character: ' + error.message);
    }
}

// Make function available globally
window.deleteCharacter = deleteCharacter;
// Make function available globally
window.deleteCharacter = deleteCharacter;

// Function to edit character

async function editCharacter(characterId) {
    try {
        const response = await fetch(`/characters/${characterId}/data`, {
            credentials: 'include'
        });

        if (!response.ok) {
            if (response.status === 404) {
                throw new Error('Character not found');
            } else if (response.status === 403) {
                throw new Error('You do not have permission to edit this character');
            }
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to load character data');
        }

        const character = await response.json();
        
        // Redirect to edit page
        window.location.href = `/edit-character/${characterId}`;

    } catch (error) {
        console.error('Error editing character:', error);
        alert(error.message);
    }
}

// Function to create character card
function createCharacterCard(character) {
    const card = document.createElement('div');
    card.className = 'character-card';
    card.setAttribute('data-character-id', character.id);

    const avatarPath = character.avatar || character.avatar_path || './default-avatar.jpg';

    const tagsHtml = character.settings?.tags?.map(tag => 
        `<span class="tag">${tag}</span>`
    ).join('') || '';

    card.innerHTML = `
        <img src="${avatarPath}" alt="${character.name}" class="character-image">
        <div class="character-info">
            <h2>${character.name}</h2>
            <p class="description">${character.description || ''}</p>
            <div class="character-meta">
                ${tagsHtml}
            </div>
            <div class="card-actions">
                <button class="edit-btn" onclick="editCharacter('${character.id}')">Edit</button>
                <button class="delete-btn" onclick="deleteCharacter('${character.id}')">Delete</button>
            </div>
            ${character.rejectionReason ? 
                `<div class="rejection-reason">
                    Rejection reason: ${character.rejectionReason}
                </div>` : ''
            }
        </div>
    `;

    return card;
}

// Function to load characters
async function loadCharacters() {
    try {
        const response = await fetch('/characters/my-library', {
            credentials: 'include'
        });
        
        if (!response.ok) {
            throw new Error('Failed to load characters');
        }

        const data = await response.json();
        console.log('Loaded characters:', data);

        // Clear existing characters
        document.getElementById('private-characters').innerHTML = '';
        document.getElementById('public-characters').innerHTML = '';
        document.getElementById('pending-characters').innerHTML = '';

        // Handle empty states
        ['private', 'public', 'pending'].forEach(type => {
            const container = document.getElementById(`${type}-characters`);
            if (!data[type] || data[type].length === 0) {
                container.innerHTML = `<p class="no-characters">No ${type} characters found</p>`;
                return;
            }
        });

        // Populate character lists
        data.private.forEach(character => {
            document.getElementById('private-characters').appendChild(createCharacterCard(character));
        });

        data.public.forEach(character => {
            document.getElementById('public-characters').appendChild(createCharacterCard(character));
        });

        data.pending.forEach(character => {
            document.getElementById('pending-characters').appendChild(createCharacterCard(character));
        });

    } catch (error) {
        console.error('Error loading characters:', error);
        alert('Failed to load characters');
    }
}

// Tab switching functionality
function setupTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            // Update active tab button
            tabButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');

            // Update active tab content
            const tabName = button.dataset.tab;
            document.querySelectorAll('.character-list').forEach(list => {
                list.classList.remove('active');
            });
            document.getElementById(`${tabName}-characters`).classList.add('active');
        });
    });
}

// Logout functionality
function setupLogout() {
    const logoutButton = document.getElementById('logout-button');
    if (logoutButton) {
        logoutButton.addEventListener('click', async () => {
            try {
                const response = await fetch('/auth/logout', {
                    credentials: 'include'
                });
                
                if (response.ok) {
                    window.location.href = '/login';
                } else {
                    throw new Error('Logout failed');
                }
            } catch (error) {
                console.error('Error during logout:', error);
                alert('Failed to logout');
            }
        });
    }
}

// Initialize everything when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    setupTabs();
    setupLogout();
    loadCharacters();

    // Check for admin status and show/hide admin button
    fetch('/auth/user', {
        credentials: 'include'
    })
    .then(response => response.json())
    .then(data => {
        if (data.user && data.user.is_admin) {
            document.querySelector('.admin-only')?.style.removeProperty('display');
        }
        if (data.user) {
            document.getElementById('username-display').textContent = data.user.username;
            document.getElementById('credits-display').textContent = `${data.user.credits} credits`;
        }
    })
    .catch(error => console.error('Error checking admin status:', error));
});

// Make functions available globally
window.deleteCharacter = deleteCharacter;
window.editCharacter = editCharacter;
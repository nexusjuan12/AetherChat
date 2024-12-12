class CharacterLibrary {
    constructor() {
        this.activeTab = 'private';
        this.characters = {
            private: [],
            public: [],
            pending: []
        };
        console.log('CharacterLibrary initialized');
        this.init();
    }

    async init() {
        console.log('Starting initialization');
        await this.loadCharacters();
        this.setupEventListeners();
    }

    async loadCharacters() {
        try {
            console.log('Fetching characters...');
            const response = await fetch('/characters/my-library');
            console.log('Response:', response);
            if (response.ok) {
                const data = await response.json();
                console.log('Received data:', data);
                this.characters = data;
                this.displayCharacters(this.activeTab);
            } else {
                console.error('Failed to load characters:', await response.text());
            }
        } catch (error) {
            console.error('Error loading characters:', error);
        }
    }

    displayCharacters(tabName) {
        console.log(`Displaying ${tabName} characters:`, this.characters[tabName]);
        const containerID = `${tabName}-characters`;
        const container = document.getElementById(containerID);
        if (!container) {
            console.error(`Container ${containerID} not found`);
            return;
        }

        container.innerHTML = '';
        
        const characters = this.characters[tabName] || [];
        if (characters.length === 0) {
            console.log(`No ${tabName} characters found`);
            container.innerHTML = `<p class="no-characters">No ${tabName} characters found</p>`;
            return;
        }

        characters.forEach(character => {
            console.log('Creating card for character:', character);
            const card = this.createCharacterCard(character);
            container.appendChild(card);
        });
    }

    createCharacterCard(character) {
    const card = document.createElement('div');
    card.className = 'character-card';
    
    const avatarPath = character.avatar || character.avatar_path || './default-avatar.jpg';
    
    card.innerHTML = `
        <img src="${avatarPath}" alt="${character.name}" class="character-image">
        <div class="character-info">
            <h2>${character.name}</h2>
            <div class="character-meta">
                ${character.settings?.tags?.map(tag => `<span class="tag">${tag}</span>`).join('') || ''}
            </div>
            <div class="card-actions">
                <button class="edit-btn" data-id="${character.id}">Edit</button>
                <button class="delete-btn" data-id="${character.id}">Delete</button>
            </div>
        </div>
    `;

    // Add event listeners for the buttons
    card.querySelector('.edit-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        // Use the /edit-character/ route instead of direct HTML file
        const characterId = e.target.getAttribute('data-id');
        window.location.href = `/edit-character/${characterId}`;
    });

    card.querySelector('.delete-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        this.deleteCharacter(character.id);
    });

    return card;
}

    setupEventListeners() {
        console.log('Setting up event listeners');
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach(button => {
            button.addEventListener('click', () => {
                console.log(`Switching to tab: ${button.dataset.tab}`);
                tabButtons.forEach(btn => btn.classList.remove('active'));
                button.classList.add('active');

                const tabName = button.dataset.tab;
                this.activeTab = tabName;
                
                document.querySelectorAll('.character-list').forEach(list => {
                    list.classList.remove('active');
                });
                document.getElementById(`${tabName}-characters`).classList.add('active');
                
                this.displayCharacters(tabName);
            });
        });
    }

    async editCharacter(characterId) {
        window.location.href = `/edit-character/${characterId}`;
    }

    async deleteCharacter(characterId) {
        if (confirm('Are you sure you want to delete this character?')) {
            try {
                const response = await fetch(`/characters/${characterId}`, {
                    method: 'DELETE'
                });

                if (response.ok) {
                    await this.loadCharacters();
                } else {
                    console.error('Failed to delete character');
                }
            } catch (error) {
                console.error('Error deleting character:', error);
            }
        }
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, creating CharacterLibrary');
    new CharacterLibrary();
});

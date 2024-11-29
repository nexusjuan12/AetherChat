// State management
let characters = [];
let activeFilters = {
    categories: new Set(),
    tags: new Set(),
    search: '',
    view: 'grid',
    sort: 'random'
};

// DOM Elements
const characterGrid = document.getElementById('character-grid');
const searchInput = document.getElementById('search');
const gridViewBtn = document.getElementById('grid-view');
const listViewBtn = document.getElementById('list-view');
const sortSelect = document.getElementById('sort-select');
const categoryFilters = document.getElementById('category-filters');
const tagFilters = document.getElementById('tag-filters');
const clearFiltersBtn = document.getElementById('clear-filters');
const createCharacterBtn = document.getElementById('create-character');
const characterFormDialog = document.getElementById('character-form-dialog');
const characterForm = document.getElementById('character-form');
const closeDialogBtn = document.getElementById('close-dialog');

// Utility functions
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

function shuffleArray(array) {
    for (let i = array.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [array[i], array[j]] = [array[j], array[i]];
    }
    return array;
}

// Character loading and filtering
async function loadCharacters() {
    try {
        console.log("Starting to load characters...");
        const response = await fetch('./characters/index.json');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        const indexData = await response.json();
        console.log("Loaded index data:", indexData);
        
        characters = await Promise.all(
            indexData.characters.map(async file => {
                console.log("Loading character file:", file);
                const response = await fetch(`./characters/${file}`);
                if (!response.ok) {
                    console.error(`Failed to load character file: ${file}`);
                    return null;
                }
                const data = await response.json();
                console.log("Loaded character:", data);
                return data;
            })
        );
        
        // Filter out any failed loads
        characters = characters.filter(char => char !== null);
        
        console.log('Final loaded characters:', characters);
        
        initializeFilters();
        updateCharacterDisplay();
    } catch (error) {
        console.error('Error loading characters:', error);
        characterGrid.innerHTML = '<p class="error">Error loading characters. Please try again later.</p>';
    }
}

function initializeFilters() {
    // Collect unique categories and tags
    const categories = new Set();
    const tags = new Set();
    
    characters.forEach(char => {
        if (char.category) categories.add(char.category);
        char.tags?.forEach(tag => tags.add(tag));
    });
    
    // Create filter buttons
    categoryFilters.innerHTML = '';
    categories.forEach(category => {
        const btn = createFilterButton(category, 'category');
        categoryFilters.appendChild(btn);
    });
    
    tagFilters.innerHTML = '';
    tags.forEach(tag => {
        const btn = createFilterButton(tag, 'tag');
        tagFilters.appendChild(btn);
    });
}

function createFilterButton(value, type) {
    const button = document.createElement('button');
    button.classList.add('filter-option');
    button.textContent = value;
    button.addEventListener('click', () => toggleFilter(value, type));
    return button;
}

function toggleFilter(value, type) {
    const filterSet = type === 'category' ? activeFilters.categories : activeFilters.tags;
    const button = [...document.querySelectorAll('.filter-option')]
        .find(btn => btn.textContent === value);
    
    if (filterSet.has(value)) {
        filterSet.delete(value);
        button.classList.remove('active');
    } else {
        filterSet.add(value);
        button.classList.add('active');
    }
    
    updateCharacterDisplay();
}

function filterCharacters() {
    return characters.filter(char => {
        const matchesSearch = char.name.toLowerCase().includes(activeFilters.search.toLowerCase()) ||
                            char.description.toLowerCase().includes(activeFilters.search.toLowerCase());
        const matchesCategories = activeFilters.categories.size === 0 || 
                                (char.category && activeFilters.categories.has(char.category));
        const matchesTags = activeFilters.tags.size === 0 ||
                          (char.tags && char.tags.some(tag => activeFilters.tags.has(tag)));
        
        return matchesSearch && matchesCategories && matchesTags;
    });
}

function sortCharacters(chars) {
    switch (activeFilters.sort) {
        case 'name':
            return [...chars].sort((a, b) => a.name.localeCompare(b.name));
        case 'newest':
            return [...chars].sort((a, b) => new Date(b.dateAdded) - new Date(a.dateAdded));
        case 'category':
            return [...chars].sort((a, b) => (a.category || '').localeCompare(b.category || ''));
        case 'random':
            return shuffleArray([...chars]);
        default:
            return chars;
    }
}

function updateCharacterDisplay() {
    const filteredChars = filterCharacters();
    const sortedChars = sortCharacters(filteredChars);
    
    characterGrid.className = activeFilters.view === 'list' ? 'list-view' : 'grid-view';
    characterGrid.innerHTML = '';
    
    if (sortedChars.length === 0) {
        characterGrid.innerHTML = '<p class="no-results">No characters found matching your criteria.</p>';
        return;
    }
    
    sortedChars.forEach(char => {
        const card = createCharacterCard(char);
        characterGrid.appendChild(card);
    });
}

function createCharacterCard(char) {
    const card = document.createElement('div');
    card.classList.add('character-card');
    
    const tagsHtml = char.tags ? 
        char.tags.map(tag => `<span class="tag">${tag}</span>`).join('') : '';
    
    card.innerHTML = `
        <img class="character-image" src="${char.avatar}" alt="${char.name}" onerror="this.src='./avatars/default-user.png'">
        <div class="character-info">
            <h2>${char.name}</h2>
            <p>${char.description}</p>
            <div class="character-meta">
                ${char.category ? `<span class="category-badge">${char.category}</span>` : ''}
                ${tagsHtml}
            </div>
        </div>
    `;
    
    card.addEventListener('click', () => {
        sessionStorage.setItem('selectedCharacter', JSON.stringify(char));
        window.location.href = './chat/chat.html';
    });
    
    return card;
}

function clearFilters() {
    activeFilters.categories.clear();
    activeFilters.tags.clear();
    activeFilters.search = '';
    searchInput.value = '';
    document.querySelectorAll('.filter-option').forEach(btn => 
        btn.classList.remove('active'));
    updateCharacterDisplay();
}

// Event Listeners
searchInput?.addEventListener('input', debounce(e => {
    activeFilters.search = e.target.value;
    updateCharacterDisplay();
}, 300));

gridViewBtn?.addEventListener('click', () => {
    activeFilters.view = 'grid';
    gridViewBtn.classList.add('active');
    listViewBtn.classList.remove('active');
    updateCharacterDisplay();
});

listViewBtn?.addEventListener('click', () => {
    activeFilters.view = 'list';
    listViewBtn.classList.add('active');
    gridViewBtn.classList.remove('active');
    updateCharacterDisplay();
});

sortSelect?.addEventListener('change', e => {
    activeFilters.sort = e.target.value;
    updateCharacterDisplay();
});

clearFiltersBtn?.addEventListener('click', clearFilters);

createCharacterBtn?.addEventListener('click', () => {
    characterFormDialog.showModal();
});

closeDialogBtn?.addEventListener('click', () => {
    characterFormDialog.close();
});

characterForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(characterForm);
    const newCharacter = {
        id: formData.get('name').toLowerCase().replace(/\s+/g, '-'),
        name: formData.get('name'),
        description: formData.get('description'),
        systemPrompt: formData.get('systemPrompt'),
        category: formData.get('category'),
        tags: formData.get('tags').split(',').map(tag => tag.trim()),
        avatar: formData.get('avatar'),
        ttsVoice: formData.get('ttsVoice'),
        sex: formData.get('sex'),
        orientation: formData.get('orientation'),
        nsfw: formData.get('nsfw') === 'true',
        dateAdded: new Date().toISOString()
    };
    
    // In a real application, you would save this to the server
    characters.push(newCharacter);
    updateCharacterDisplay();
    characterFormDialog.close();
});

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
    const initApp = async () => {
        try {
            // Wait a moment for styles to load
            await new Promise(resolve => setTimeout(resolve, 100));
            // Initialize the app
            await loadCharacters();
        } catch (error) {
            console.error('Error initializing app:', error);
        }
    };

    initApp();
});
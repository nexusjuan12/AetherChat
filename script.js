import { currentUser, checkAuth } from './auth.js';

// State management
let characters = [];
let activeFilters = {
    categories: new Set(),
    tags: new Set(),
    search: '',
    view: 'grid',
    sort: 'random'
};

// Load characters from the index
async function loadCharacters() {
    try {
        console.log("Fetching character index...");
        const response = await fetch('./characters/index.json');
        if (!response.ok) throw new Error(`Failed to load character index: ${response.status}`);

        const data = await response.json();
        console.log("Character index loaded:", data);

        // Load individual character files
        characters = await Promise.all(
    data.characters.map(async (file) => {
        try {
            const response = await fetch(`./characters/${file}`);
            if (!response.ok) throw new Error(`Failed to load character file: ${file}`);
            return await response.json();
        } catch (error) {
            console.error(error);
            return null;
        }
    })
);

// Only filter private characters
characters = characters.filter((char) => {
    if (!char) return false;
    if (char.isPrivate) {
        return currentUser && char.creator === currentUser.id;
    }
    return true;  // Show all non-private characters
});
        

        // Filter out null values and private characters unless they belong to the user
        characters = characters.filter((char) => {
            if (!char) return false;
            if (char.isPrivate) {
                return currentUser && char.creator === currentUser.id;
            }
            return true;
        });

        console.log("Final character list:", characters);
        initializeFilters();
        updateCharacterDisplay();
    } catch (error) {
        console.error('Error loading characters:', error);
        characters = [];
        updateCharacterDisplay();
    }
}

// Initialize filters
function initializeFilters() {
    const categories = new Set();
    const tags = new Set();

    characters.forEach((char) => {
        if (char.category) categories.add(char.category);
        if (char.tags) char.tags.forEach((tag) => tags.add(tag));
    });

    const categoryFilters = document.getElementById('category-filters');
    const tagFilters = document.getElementById('tag-filters');
    
    if (categoryFilters) {
        categoryFilters.innerHTML = '';
        Array.from(categories).sort().forEach((category) => {
            const btn = createFilterButton(category, 'category');
            categoryFilters.appendChild(btn);
        });
    }

    if (tagFilters) {
        tagFilters.innerHTML = '';
        Array.from(tags).sort().forEach((tag) => {
            const btn = createFilterButton(tag, 'tag');
            tagFilters.appendChild(btn);
        });
    }
}

function createFilterButton(value, type) {
    const button = document.createElement('button');
    button.classList.add('filter-button');
    // Check if the filter set exists before trying to use it
    const filterSet = type === 'category' ? activeFilters.categories : activeFilters.tags;
    if (filterSet && filterSet.has(value)) {
        button.classList.add('active');
    }
    button.textContent = value;
    button.addEventListener('click', () => toggleFilter(value, type));
    return button;
}

function toggleFilter(value, type) {
    const filterSet = type === 'category' ? activeFilters.categories : activeFilters.tags;
    if (filterSet.has(value)) {
        filterSet.delete(value);
    } else {
        filterSet.add(value);
    }
    updateCharacterDisplay();
}

// Update character display
function updateCharacterDisplay() {
    const characterGrid = document.getElementById('character-grid');
    if (!characterGrid) return;

    const filteredChars = filterCharacters();
    const sortedChars = sortCharacters(filteredChars);

    characterGrid.innerHTML = '';

    if (sortedChars.length === 0) {
        const noResults = document.createElement('p');
        noResults.className = 'no-results';
        noResults.textContent = currentUser ? 
            'No characters found. Try creating one!' : 
            'No characters found. Try logging in to see more!';
        characterGrid.appendChild(noResults);
        return;
    }

    sortedChars.forEach((char) => {
        const card = createCharacterCard(char);
        characterGrid.appendChild(card);
    });
}

function filterCharacters() {
    return characters.filter((char) => {
        const matchesSearch = char.name.toLowerCase().includes(activeFilters.search.toLowerCase()) ||
                            char.description.toLowerCase().includes(activeFilters.search.toLowerCase());
        const matchesCategories = !activeFilters.categories.size || 
                                activeFilters.categories.has(char.category);
        const matchesTags = !activeFilters.tags.size || 
                          char.tags?.some((tag) => activeFilters.tags.has(tag));
        return matchesSearch && matchesCategories && matchesTags;
    });
}

function sortCharacters(chars) {
    const charsCopy = [...chars];
    switch (activeFilters.sort) {
        case 'name':
            charsCopy.sort((a, b) => a.name.localeCompare(b.name));
            break;
        case 'newest':
            charsCopy.sort((a, b) => new Date(b.dateAdded) - new Date(a.dateAdded));
            break;
        case 'random':
        default:
            for (let i = charsCopy.length - 1; i > 0; i--) {
                const j = Math.floor(Math.random() * (i + 1));
                [charsCopy[i], charsCopy[j]] = [charsCopy[j], charsCopy[i]];
            }
    }
    return charsCopy;
}

function createCharacterCard(char) {
    const card = document.createElement('div');
    card.classList.add('character-card');

    const tagsHtml = char.tags
        ? char.tags.map((tag) => `<span class="tag">${tag}</span>`).join('')
        : '';

    card.innerHTML = `
        <img class="character-image" src="${char.avatar}" alt="${char.name}" 
             onerror="this.src='./avatars/default-user.png'">
        <div class="character-info">
            <h2>${char.name}</h2>
            <p>${char.description}</p>
            <div class="character-meta">
                ${char.category ? `<span class="category-badge">${char.category}</span>` : ''}
                ${tagsHtml}
                ${char.isPrivate ? '<span class="private-badge">Private</span>' : ''}
            </div>
        </div>
    `;

    card.addEventListener('click', () => {
    if (!currentUser) {
        sessionStorage.setItem('selectedCharacter', JSON.stringify(char));
        window.location.href = './login.html';
        return;
    }
    sessionStorage.setItem('selectedCharacter', JSON.stringify(char));
    window.location.href = './chat/chat.html';
});

    return card;
}

// Event Listeners
document.addEventListener('DOMContentLoaded', async () => {
    await checkAuth();
    loadCharacters();

    const searchInput = document.getElementById('search');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            activeFilters.search = e.target.value;
            updateCharacterDisplay();
        });
    }
});

// Export functions that might be needed by other modules
export {
    loadCharacters,
    updateCharacterDisplay
};
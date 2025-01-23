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

// Load characters from the server
async function loadCharacters() {
    try {
        console.log("Loading characters...");
        const response = await fetch('/characters/my-library', {
            credentials: 'include'
        });
        
        if (!response.ok) throw new Error(`Failed to load characters: ${response.status}`);
        
        const data = await response.json();
        console.log("Raw character data:", data);

        characters = [];
        
        if (currentUser) {
            // Load approved public characters
            const publicChars = data.public || [];
            
            // Load user's private characters
            const privateChars = data.private || [];
            
            // Load pending characters (only the user's own pending characters)
            const pendingChars = (data.pending || []).filter(char => 
                char.creator === currentUser.id
            );
            
            characters = [
                ...publicChars,
                ...privateChars,
                ...pendingChars
            ];
        } else {
            // Only show approved public characters for non-logged in users
            characters = data.public?.filter(char => char.isApproved) || [];
        }

        // Filter out null values and validate character objects
        characters = characters.filter(char => {
            if (!char) return false;
            if (!char.name) {
                console.warn("Found character without name:", char);
                return false;
            }
            return true;
        });

        console.log("Processed character list:", characters);
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
        if (card) characterGrid.appendChild(card);
    });
}

function filterCharacters() {
    return characters.filter((char) => {
        if (!char) return false;
        
        const name = char.name || '';
        const description = char.description || '';
        const category = char.category || '';
        const charTags = char.tags || [];

        const matchesSearch = (name.toLowerCase().includes(activeFilters.search.toLowerCase()) ||
                             description.toLowerCase().includes(activeFilters.search.toLowerCase()));
                             
        const matchesCategories = !activeFilters.categories.size || 
                                activeFilters.categories.has(category);
                                
        const matchesTags = !activeFilters.tags.size || 
                           charTags.some((tag) => activeFilters.tags.has(tag));

        return matchesSearch && matchesCategories && matchesTags;
    });
}

function sortCharacters(chars) {
    const charsCopy = [...chars];
    switch (activeFilters.sort) {
        case 'name':
            charsCopy.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
            break;
        case 'newest':
            charsCopy.sort((a, b) => new Date(b.dateAdded || 0) - new Date(a.dateAdded || 0));
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
    if (!char) return null;

    const card = document.createElement('div');
    card.classList.add('character-card');

    const name = char.name || 'Unnamed Character';
    const description = char.description || 'No description available';
    const avatar = char.avatar || './avatars/default-user.png';
    const category = char.category || '';
    const tags = char.tags || [];
    const isPrivate = char.isPrivate || false;
    const isPending = char.approvalStatus === 'pending';
    const isCreator = currentUser && char.creator === currentUser.id;

    // Status badge logic
    let statusBadge = '';
    if (isPrivate) {
        statusBadge = '<span class="private-badge">Private</span>';
    } else if (isPending) {
        if (isCreator) {
            statusBadge = '<span class="pending-badge">Pending Approval</span>';
        } else {
            return null; // Don't show pending characters from other users
        }
    }

    const tagsHtml = tags
        .map((tag) => `<span class="tag">${tag}</span>`)
        .join('');

    card.innerHTML = `
        <img class="character-image" src="${avatar}" alt="${name}" 
             onerror="this.src='./avatars/default-user.png'">
        <div class="character-info">
            <h2>${name}</h2>
            <p>${description}</p>
            <div class="character-meta">
                ${category ? `<span class="category-badge">${category}</span>` : ''}
                ${tagsHtml}
                ${statusBadge}
            </div>
        </div>
    `;

    card.addEventListener('click', () => {
        // Access rules:
        // 1. Public and approved characters - everyone can access
        // 2. Private characters - only creator can access
        // 3. Pending characters - only creator can access
        if (!currentUser) {
            if (!isPending && !isPrivate) {
                sessionStorage.setItem('selectedCharacter', JSON.stringify(char));
                window.location.href = './chat/chat.html';
            } else {
                window.location.href = '/login';
            }
            return;
        }

        if (isCreator || (!isPrivate && !isPending)) {
            sessionStorage.setItem('selectedCharacter', JSON.stringify(char));
            window.location.href = './chat/chat.html';
        }
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

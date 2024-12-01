// Constants
const API_CHAT_URL = '/v1/chat/completions';
const API_TTS_URL = '/api/tts';
const CHARACTER_INDEX_URL = '/characters/index.json';

// Utility: Debounce function
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

// Utility: Shuffle array
function shuffleArray(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
  return array;
}

// State management
let characters = [];
let activeFilters = {
  categories: new Set(),
  tags: new Set(),
  search: '',
  view: 'grid',
  sort: 'random',
};

// Load characters from the index
async function loadCharacters() {
  try {
    console.log("Fetching character index...");
    const response = await fetch(CHARACTER_INDEX_URL);
    if (!response.ok) throw new Error(`Failed to load character index: ${response.status}`);

    const data = await response.json();
    console.log("Character index loaded:", data);

    // Load individual character files
    characters = await Promise.all(
      data.characters.map(async (file) => {
        try {
          const response = await fetch(`/characters/${file}`);
          if (!response.ok) throw new Error(`Failed to load character file: ${file}`);
          return await response.json();
        } catch (error) {
          console.error(error);
          return null;
        }
      })
    );

    // Filter out null values
    characters = characters.filter((char) => char !== null);

    console.log("Final character list:", characters);
    initializeFilters();
    updateCharacterDisplay();
  } catch (error) {
    console.error('Error loading characters:', error);
  }
}

// Initialize filters for categories and tags
function initializeFilters() {
  const categories = new Set();
  const tags = new Set();

  characters.forEach((char) => {
    if (char.category) categories.add(char.category);
    if (char.tags) char.tags.forEach((tag) => tags.add(tag));
  });

  // Populate filter UI (example elements)
  const categoryFilters = document.getElementById('category-filters');
  const tagFilters = document.getElementById('tag-filters');
  categoryFilters.innerHTML = '';
  tags.forEach((tag) => {
    const btn = createFilterButton(tag, 'tag');
    tagFilters.appendChild(btn);
  });
}

// Create filter buttons
function createFilterButton(value, type) {
  const button = document.createElement('button');
  button.classList.add('filter-option');
  button.textContent = value;
  button.addEventListener('click', () => toggleFilter(value, type));
  return button;
}

// Update displayed characters based on filters
function updateCharacterDisplay() {
  const filteredChars = filterCharacters();
  const sortedChars = sortCharacters(filteredChars);

  // Example DOM element
  const characterGrid = document.getElementById('character-grid');
  characterGrid.innerHTML = '';

  if (sortedChars.length === 0) {
    characterGrid.innerHTML = '<p>No characters found.</p>';
    return;
  }

  sortedChars.forEach((char) => {
    const card = createCharacterCard(char);
    characterGrid.appendChild(card);
  });
}

// Filter and sort logic
function filterCharacters() {
  return characters.filter((char) => {
    const matchesSearch = char.name.toLowerCase().includes(activeFilters.search.toLowerCase());
    const matchesCategories = !activeFilters.categories.size || activeFilters.categories.has(char.category);
    const matchesTags = !activeFilters.tags.size || char.tags.some((tag) => activeFilters.tags.has(tag));
    return matchesSearch && matchesCategories && matchesTags;
  });
}

function sortCharacters(chars) {
  if (activeFilters.sort === 'random') return shuffleArray([...chars]);
  return chars.sort((a, b) => a.name.localeCompare(b.name));
}

// Create a character card for display
function createCharacterCard(char) {
  const card = document.createElement('div');
  card.classList.add('character-card');

  const tagsHtml = char.tags
    ? char.tags.map((tag) => `<span class="tag">${tag}</span>`).join('')
    : '';

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

// Function to send a chat completion request
async function sendChatCompletion(payload) {
  try {
    const response = await fetch(API_CHAT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) throw new Error(`Chat completion failed: ${response.status}`);
    const data = await response.json();
    console.log("Chat completion response:", data);
    return data;
  } catch (error) {
    console.error('Error sending chat completion:', error);
  }
}

// Function to send a TTS request
async function sendTTSRequest(text, rvcModel, edgeVoice, ttsRate = 0, rvcPitch = 0) {
  try {
    const payload = {
      text: text,
      rvc_model: rvcModel,
      edge_voice: edgeVoice,
      tts_rate: ttsRate,
      rvc_pitch: rvcPitch,
    };

    const response = await fetch(API_TTS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) throw new Error(`TTS request failed: ${response.status}`);
    const data = await response.json();
    console.log("TTS response:", data);
    return data.audio_url;
  } catch (error) {
    console.error('Error sending TTS request:', error);
  }
}

// Event listeners
document.getElementById('search')?.addEventListener(
  'input',
  debounce((e) => {
    activeFilters.search = e.target.value;
    updateCharacterDisplay();
  }, 300)
);

// Example function to test Chat Completion and TTS
async function testChatAndTTS() {
  const chatPayload = { prompt: "Tell me a story.", max_tokens: 100 };
  const chatResponse = await sendChatCompletion(chatPayload);

  if (chatResponse && chatResponse.choices && chatResponse.choices[0]) {
    const text = chatResponse.choices[0].text;
    console.log("Chat response text:", text);

    const ttsUrl = await sendTTSRequest(text, 'default_rvc', 'en-US-JennyNeural');
    console.log("Generated TTS audio URL:", ttsUrl);

    if (ttsUrl) {
      const audio = new Audio(ttsUrl);
      audio.play();
    }
  }
}

// Initialize the application
document.addEventListener('DOMContentLoaded', () => {
  loadCharacters();
});

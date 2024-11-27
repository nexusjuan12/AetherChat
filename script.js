import { characters } from "./characters.js";

function loadCharacters() {
    const grid = document.getElementById("character-grid");
    
    characters.forEach(character => {
        // Create character card
        const card = document.createElement("div");
        card.classList.add("character-card");

        card.innerHTML = `
            <img src="${character.avatar}" alt="${character.name}">
            <div class="info">
                <h2>${character.name}</h2>
                <p>${character.description}</p>
            </div>
        `;

        // On click, save character data and redirect to chat
        card.addEventListener("click", () => {
            sessionStorage.setItem("selectedCharacter", JSON.stringify(character));
            window.location.href = "./chat.html";
        });

        // Append card to the grid
        grid.appendChild(card);
    });
}

// Load characters on page load
window.onload = loadCharacters;

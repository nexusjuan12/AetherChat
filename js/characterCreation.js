async function csrfHeaders() {
    const response = await fetch('/auth/csrf', { credentials: 'include' });
    if (!response.ok) throw new Error('Your login has expired.');
    const { csrf_token } = await response.json();
    return { 'X-CSRF-Token': csrf_token };
}

function characterId(name) {
    const value = name.toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-|-$/g, '');
    if (!value) throw new Error('Use at least one letter or number in the character name.');
    return value;
}

async function loadVoiceProfiles() {
    const select = document.getElementById('voice-profile');
    const response = await fetch('/api/voice-profiles', { credentials: 'include' });
    if (!response.ok) return;
    for (const profile of await response.json()) {
        const option = document.createElement('option');
        option.value = profile.id;
        option.textContent = `${profile.display_name} (${profile.visibility})`;
        select.appendChild(option);
    }
}

async function uploadFile(endpoint, field, file, id, headers) {
    const payload = new FormData();
    payload.append(field, file);
    payload.append('characterId', id);
    const response = await fetch(endpoint, { method: 'POST', headers, body: payload, credentials: 'include' });
    if (!response.ok) throw new Error((await response.json()).error || `Unable to upload ${field}.`);
    return response.json();
}

document.addEventListener('DOMContentLoaded', () => {
    loadVoiceProfiles();
    document.getElementById('characterForm').addEventListener('submit', async event => {
        event.preventDefault();
        const status = document.getElementById('status');
        const button = event.currentTarget.querySelector('button[type="submit"]');
        button.disabled = true;
        status.textContent = 'Preparing character...';
        try {
            const name = document.getElementById('name').value.trim();
            const id = characterId(name);
            const avatar = document.getElementById('avatar').files[0];
            const background = document.getElementById('background').files[0];
            if (!avatar || !background) throw new Error('Avatar and background are required.');
            const headers = await csrfHeaders();
            status.textContent = 'Uploading media...';
            const [avatarData, backgroundData] = await Promise.all([
                uploadFile('/upload/avatar', 'avatar', avatar, id, headers),
                uploadFile('/upload/character-background', 'background', background, id, headers),
            ]);
            const greetings = document.getElementById('greetings').value
                .split('\n').map(line => line.trim()).filter(Boolean);
            status.textContent = 'Creating character...';
            const response = await fetch('/characters/create', {
                method: 'POST', credentials: 'include',
                headers: { ...headers, 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id, name,
                    category: document.getElementById('category').value.trim() || 'Other',
                    description: document.getElementById('description').value.trim(),
                    systemPrompt: document.getElementById('systemPrompt').value.trim(),
                    greetings,
                    avatar: avatarData.avatarPath,
                    background: backgroundData.backgroundPath,
                    is_private: document.getElementById('private').checked,
                    tts_rate: Number(document.getElementById('tts-rate').value),
                    voice_profile_id: document.getElementById('voice-profile').value || null,
                }),
            });
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'Character creation failed.');
            window.location.assign('/my-library');
        } catch (error) {
            status.textContent = error.message;
        } finally {
            button.disabled = false;
        }
    });
});

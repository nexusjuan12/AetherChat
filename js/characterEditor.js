document.addEventListener('DOMContentLoaded', () => {
    // Get character ID from URL
    const characterId = window.location.pathname.split('/').pop();
    const form = document.getElementById('characterForm');

    // Function to update slider displays
    const updateSliderDisplays = () => {
        document.querySelectorAll('.slider-control input[type="range"]').forEach(slider => {
            const display = slider.nextElementSibling;
            display.textContent = slider.value;
        });
    };

    // Set up slider event listeners
    document.querySelectorAll('.slider-control input[type="range"]').forEach(slider => {
        const display = slider.nextElementSibling;
        slider.addEventListener('input', () => {
            display.textContent = slider.value;
        });
    });

    // Handle voice model type selection
    const voiceModelType = document.getElementById('voiceModelType');
    const existingModelSection = document.getElementById('existingModelSection');
    const modelUploadSection = document.getElementById('modelUploadSection');

    voiceModelType.addEventListener('change', () => {
        existingModelSection.style.display = voiceModelType.value === 'existing' ? 'block' : 'none';
        modelUploadSection.style.display = voiceModelType.value === 'upload' ? 'block' : 'none';
        
        // Load voice models when "existing" is selected
        if (voiceModelType.value === 'existing') {
            loadVoiceModels();
        }
    });

    // Function to load available voice models
    async function loadVoiceModels() {
        try {
            const response = await fetch('/api/available-voices');
            if (!response.ok) throw new Error('Failed to fetch voice models');
            const data = await response.json();
            
            const modelSelect = document.getElementById('existingCharacterModel');
            if (!modelSelect) {
                console.error('existingCharacterModel select element not found');
                return;
            }

            // Clear existing options
            modelSelect.innerHTML = '<option value="">Select a Character\'s Voice Model</option>';
            
            if (data.rvc_models && Array.isArray(data.rvc_models)) {
                data.rvc_models.forEach(modelId => {
                    const option = document.createElement('option');
                    option.value = modelId;
                    option.textContent = modelId.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                    modelSelect.appendChild(option);
                });
            }
        } catch (error) {
            console.error('Error loading voice models:', error);
        }
    }

    // Fetch and populate character data
    fetch(`/characters/${characterId}/data`)
        .then(response => response.json())
        .then(data => {
            console.log('Received character data:', data);  // Debug log
            // Basic Info
            document.getElementById('name').value = data.name || '';
            document.getElementById('category').value = data.category || '';
            document.getElementById('description').value = data.description || '';
            document.getElementById('systemPrompt').value = data.systemPrompt || '';
            
            // Greetings
            if (Array.isArray(data.greetings)) {
                document.getElementById('greetings').value = data.greetings.join('\n');
            } else if (data.greeting) {
                document.getElementById('greetings').value = data.greeting;
            }
            
            // Voice Settings
            document.getElementById('ttsVoice').value = data.ttsVoice || '';
            document.getElementById('tts_rate').value = data.tts_rate || 0;
            document.getElementById('rvc_pitch').value = data.rvc_pitch || 0;
            
            // If character has an RVC model, set voice model type and selection
            if (data.rvc_model) {
                voiceModelType.value = 'existing';
                existingModelSection.style.display = 'block';
                loadVoiceModels().then(() => {
                    const modelSelect = document.getElementById('existingCharacterModel');
                    if (modelSelect) {
                        modelSelect.value = data.rvc_model;
                    }
                });
            }
            
            // Visibility
            document.getElementById('isPrivate').checked = data.isPrivate || false;
            
            // Update all slider displays
            updateSliderDisplays();
            
            // Show existing media previews
            if (data.avatar) {
                const avatarPreview = document.getElementById('avatarPreview');
                avatarPreview.innerHTML = `<img src="${data.avatar}" alt="Character Avatar">`;
            }
            if (data.background) {
                const backgroundPreview = document.getElementById('backgroundPreview');
                backgroundPreview.innerHTML = `<img src="${data.background}" alt="Character Background">`;
            }
        })
        .catch(error => {
            console.error('Error loading character data:', error);
            alert('Failed to load character data');
        });

    // Handle form submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const formData = new FormData(form);
        
        try {
            const jsonData = {};
            formData.forEach((value, key) => {
                // Skip empty file inputs
                if ((key === 'modelFile' || key === 'indexFile' || key === 'avatar' || key === 'background') && 
                    (value instanceof File && value.size === 0)) {
                    return;
                }
                
                // Handle special cases
                if (key === 'isPrivate') {
                    jsonData[key] = value === 'on';
                } else {
                    jsonData[key] = value;
                }
            });

            // Add existing avatar and background paths if no new files
            const avatarPreview = document.getElementById('avatarPreview');
            const backgroundPreview = document.getElementById('backgroundPreview');
            
            if (!jsonData.avatar && avatarPreview) {
                const avatarImg = avatarPreview.querySelector('img');
                if (avatarImg) {
                    jsonData.avatar = avatarImg.src.replace(window.location.origin, '');
                }
            }
            
            if (!jsonData.background && backgroundPreview) {
                const backgroundImg = backgroundPreview.querySelector('img');
                if (backgroundImg) {
                    jsonData.background = backgroundImg.src.replace(window.location.origin, '');
                }
            }

            // Add voice settings
            jsonData.tts_rate = parseInt(formData.get('tts_rate')) || 0;
            jsonData.rvc_pitch = parseInt(formData.get('rvc_pitch')) || 0;

            // Handle RVC model selection
            if (voiceModelType.value === 'existing') {
                const existingModel = formData.get('existingCharacterModel');
                if (existingModel) {
                    jsonData.rvc_model = existingModel;
                }
            }

            // Remove empty file inputs
            delete jsonData.modelFile;
            delete jsonData.indexFile;

            // Convert greetings from text area to array
            if (jsonData.greetings) {
                jsonData.greetings = jsonData.greetings.split('\n').filter(greeting => greeting.trim());
            }

            console.log('Sending JSON data:', jsonData);

            const response = await fetch(`/characters/${characterId}/update`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(jsonData)
            });
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('Server response:', errorText);
                throw new Error(`Failed to update character: ${errorText}`);
            }
            
            const result = await response.json();
            console.log('Update successful:', result);
            
            alert('Character updated successfully!');
            window.location.href = '/my-library';
            
        } catch (error) {
            console.error('Error updating character:', error);
            alert('Error updating character: ' + error.message);
        }
    });

    // Handle delete button
    document.getElementById('deleteCharacter')?.addEventListener('click', async () => {
        if (confirm('Are you sure you want to delete this character? This action cannot be undone.')) {
            try {
                const response = await fetch(`/delete-character/${characterId}`, {
                    method: 'POST'
                });
                
                if (!response.ok) throw new Error('Failed to delete character');
                
                alert('Character deleted successfully!');
                window.location.href = '/my-library';
                
            } catch (error) {
                console.error('Error deleting character:', error);
                alert('Failed to delete character');
            }
        }
    });
});

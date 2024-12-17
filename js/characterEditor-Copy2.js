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
            const response = await fetch('/api/available-voices', {
                credentials: 'include'
            });
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

    // Handle file uploads with progress bars
    const setupFileUpload = (inputId, previewId, progressBar) => {
        const input = document.getElementById(inputId);
        const preview = document.getElementById(previewId);
        
        if (!input) return;

        input.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            // Handle model and index files
            if (inputId === 'modelFile' || inputId === 'indexFile') {
                const formData = new FormData();
                formData.append('characterId', characterId);
                
                if (inputId === 'modelFile') {
                    if (!file.name.endsWith('.pth')) {
                        alert('Please upload a .pth file for the model');
                        return;
                    }
                    formData.append('modelFile', file);
                } else {
                    if (!file.name.endsWith('.index')) {
                        alert('Please upload a .index file');
                        return;
                    }
                    formData.append('indexFile', file);
                }

                progressBar.style.width = '0%';
                progressBar.textContent = 'Starting upload...';

                try {
                    const response = await fetch('/characters/upload-model', {
                        method: 'POST',
                        body: formData,
                        credentials: 'include'
                    });

                    if (!response.ok) {
                        const errorText = await response.text();
                        console.error('Upload error response:', errorText);
                        throw new Error(errorText || 'Failed to upload file');
                    }
                    
                    const result = await response.json();
                    console.log(`${inputId} upload response:`, result);
                    
                    progressBar.style.width = '100%';
                    progressBar.textContent = 'Upload complete';

                    // If both files are uploaded, show success message
                    const modelInput = document.getElementById('modelFile');
                    const indexInput = document.getElementById('indexFile');
                    if (modelInput.files.length > 0 && indexInput.files.length > 0) {
                        alert('Voice model files uploaded successfully!');
                    }

                } catch (error) {
                    console.error(`Error uploading ${inputId}:`, error);
                    progressBar.style.width = '0%';
                    progressBar.textContent = 'Upload failed';
                    alert(`Failed to upload ${inputId}: ${error.message}`);
                }
            } else {
                // Handle media file upload (avatar/background)
                if (file.type.startsWith('image/') || file.type.startsWith('video/')) {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        if (file.type.startsWith('video/')) {
                            preview.innerHTML = `
                                <video controls>
                                    <source src="${e.target.result}" type="${file.type}">
                                    Your browser does not support the video tag.
                                </video>`;
                        } else {
                            preview.innerHTML = `<img src="${e.target.result}" alt="Preview">`;
                        }
                    };
                    reader.readAsDataURL(file);
                }
            }
        });
    };

    // Set up file upload handlers
    const setupFileUploads = () => {
        setupFileUpload('avatar', 'avatarPreview', document.querySelector('#avatar + .progress-bar .progress'));
        setupFileUpload('background', 'backgroundPreview', document.querySelector('#background + .progress-bar .progress'));
        setupFileUpload('modelFile', null, document.querySelector('#modelFile + .progress-bar .progress'));
        setupFileUpload('indexFile', null, document.querySelector('#indexFile + .progress-bar .progress'));
    };

    setupFileUploads();
    
    // Fetch and populate character data
    fetch(`/characters/${characterId}/data`, {
        credentials: 'include'
    })
    .then(response => {
        if (!response.ok) throw new Error('Failed to load character data');
        return response.json();
    })
    .then(data => {
        console.log('Received character data:', data);

        // Basic Info
        document.getElementById('name').value = data.name || '';
        document.getElementById('category').value = data.category || '';
        
        // Fix description parsing - remove the JSON artifacts if present
        let description = data.description || '';
        if (typeof description === 'string') {
            description = description.replace(/^"description":\s*"|",$/, '');
        }
        document.getElementById('description').value = description;
        
        // System Prompt and TTS Voice
        document.getElementById('systemPrompt').value = data.system_prompt || data.systemPrompt || '';
        document.getElementById('ttsVoice').value = data.tts_voice || data.ttsVoice || '';

        // Voice Settings
        document.getElementById('tts_rate').value = data.tts_rate || 0;
        document.getElementById('rvc_pitch').value = data.rvc_pitch || 0;

        // AI Parameters - handle both nested and flat structures
        const aiParams = data.ai_parameters || data;
        document.getElementById('temperature').value = aiParams.temperature || aiParams.ai_temperature || 0.8;
        document.getElementById('top_p').value = aiParams.top_p || aiParams.ai_top_p || 0.9;
        document.getElementById('presence_penalty').value = aiParams.presence_penalty || aiParams.ai_presence_penalty || 0.6;
        document.getElementById('frequency_penalty').value = aiParams.frequency_penalty || aiParams.ai_frequency_penalty || 0.6;
        document.getElementById('max_tokens').value = aiParams.max_tokens || aiParams.ai_max_tokens || 150;

        // Greetings - handle both array and string formats
        const greetingsField = document.getElementById('greetings');
        if (Array.isArray(data.greetings)) {
            greetingsField.value = data.greetings.join('\n');
        } else if (data.greeting) {
            greetingsField.value = data.greeting;
        } else if (typeof data.greetings === 'string') {
            greetingsField.value = data.greetings;
        }

        // RVC Model
        if (data.rvc_model) {
            const voiceModelType = document.getElementById('voiceModelType');
            const existingModelSection = document.getElementById('existingModelSection');
            
            voiceModelType.value = 'existing';
            existingModelSection.style.display = 'block';
            
            // Load voice models and set the correct one
            loadVoiceModels().then(() => {
                const modelSelect = document.getElementById('existingCharacterModel');
                if (modelSelect) {
                    modelSelect.value = data.rvc_model;
                }
            });
        }

        // Visibility
        document.getElementById('isPrivate').checked = data.is_private || data.isPrivate || false;

        // Media Previews - handle both full URLs and relative paths
        if (data.avatar) {
            const avatarPreview = document.getElementById('avatarPreview');
            const avatarUrl = data.avatar.startsWith('http') ? data.avatar : data.avatar;
            avatarPreview.innerHTML = `<img src="${avatarUrl}" alt="Character Avatar">`;
        }
        
        if (data.background) {
            const backgroundPreview = document.getElementById('backgroundPreview');
            const backgroundUrl = data.background.startsWith('http') ? data.background : data.background;
            const isVideo = backgroundUrl.match(/\.(mp4|webm|wmv)$/i);
            
            if (isVideo) {
                backgroundPreview.innerHTML = `
                    <video controls>
                        <source src="${backgroundUrl}" type="video/${isVideo[1]}">
                        Your browser does not support the video tag.
                    </video>`;
            } else {
                backgroundPreview.innerHTML = `<img src="${backgroundUrl}" alt="Character Background">`;
            }
        }

        // Update all slider displays
        updateSliderDisplays();
    })
    .catch(error => {
        console.error('Error loading character data:', error);
        alert('Failed to load character data: ' + error.message);
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
                
                if (key === 'isPrivate') {
                    jsonData[key] = value === 'on';
                } else {
                    jsonData[key] = value;
                }
            });

            // Preserve existing media paths if no new files uploaded
            const avatarPreview = document.getElementById('avatarPreview');
            const backgroundPreview = document.getElementById('backgroundPreview');
            
            if (!jsonData.avatar && avatarPreview) {
                const avatarImg = avatarPreview.querySelector('img');
                if (avatarImg) {
                    jsonData.avatar = avatarImg.src.replace(window.location.origin, '');
                }
            }
            
            if (!jsonData.background && backgroundPreview) {
                const backgroundContent = backgroundPreview.querySelector('img, video source');
                if (backgroundContent) {
                    jsonData.background = backgroundContent.src.replace(window.location.origin, '');
                }
            }

            // Voice settings
            jsonData.tts_rate = parseInt(formData.get('tts_rate')) || 0;
            jsonData.rvc_pitch = parseInt(formData.get('rvc_pitch')) || 0;

            // RVC model selection
            if (voiceModelType.value === 'existing') {
                const existingModel = formData.get('existingCharacterModel');
                if (existingModel) {
                    jsonData.rvc_model = existingModel;
                }
            }

            // AI Parameters
            jsonData.ai_parameters = {
                temperature: parseFloat(formData.get('ai_temperature')),
                top_p: parseFloat(formData.get('ai_top_p')),
                presence_penalty: parseFloat(formData.get('ai_presence_penalty')),
                frequency_penalty: parseFloat(formData.get('ai_frequency_penalty')),
                max_tokens: parseInt(formData.get('ai_max_tokens'))
            };

            // Remove unnecessary file input data
            delete jsonData.modelFile;
            delete jsonData.indexFile;

            // Convert greetings to array
            if (jsonData.greetings) {
                jsonData.greetings = jsonData.greetings.split('\n').filter(greeting => greeting.trim());
            }

            console.log('Sending update data:', jsonData);

            const response = await fetch(`/characters/${characterId}/update`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                credentials: 'include',
                body: JSON.stringify(jsonData)
            });
            
            if (!response.ok) {
                const errorText = await response.text();
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
                const response = await fetch(`/characters/${characterId}/delete`, {
                    method: 'POST',
                    credentials: 'include'
                });
                
                if (!response.ok) throw new Error('Failed to delete character');
                
                alert('Character deleted successfully!');
                window.location.href = '/my-library';
                
            } catch (error) {
                console.error('Error deleting character:', error);
                alert('Failed to delete character: ' + error.message);
            }
        }
    });
});
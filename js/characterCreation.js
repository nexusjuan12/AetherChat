class CharacterCreator {
    constructor() {
    this.form = document.getElementById('characterForm');
    console.log('CharacterCreator initialized');
    this.initializeForm();
    console.log('Loading available voices...');
    this.loadAvailableVoices();
    this.loadVoiceModels();  // Add this
    this.setupVoiceModelHandling();  // Add this
    this.setupEventListeners();
}

    initializeForm() {
    this.form.addEventListener('submit', (e) => this.handleSubmit(e));
    
    // Setup image preview
    document.querySelector('input[name="avatar"]').addEventListener('change', (e) => 
        this.handleImagePreview(e, 'avatarPreview'));
    document.querySelector('input[name="background"]').addEventListener('change', (e) => 
        this.handleImagePreview(e, 'backgroundPreview'));
}

    setupEventListeners() {
        // Update value displays for sliders
        document.querySelectorAll('.slider-control input[type="range"]').forEach(slider => {
            const display = slider.nextElementSibling;
            slider.addEventListener('input', () => {
                display.textContent = slider.value;
            });
        });
    }

    async loadAvailableVoices() {
        const edge_voices = [
            "en-GB-LibbyNeural",
            "en-GB-MaisieNeural", 
            "en-GB-RyanNeural",
            "en-GB-SoniaNeural", 
            "en-GB-ThomasNeural",
            "en-US-AvaMultilingualNeural",
            "en-US-AndrewMultilingualNeural",
            "en-US-EmmaMultilingualNeural", 
            "en-US-BrianMultilingualNeural",
            "en-US-AvaNeural",
            "en-US-AndrewNeural",
            "en-US-EmmaNeural",
            "en-US-BrianNeural",
            "en-US-AnaNeural",
            "en-US-AriaNeural",
            "en-US-ChristopherNeural",
            "en-US-EricNeural",
            "en-US-GuyNeural",
            "en-US-JennyNeural",
            "en-US-MichelleNeural",
            "en-US-RogerNeural",
            "en-US-SteffanNeural"
        ];

        try {
            const select = document.querySelector('select[name="ttsVoice"]');
            if (!select) {
                throw new Error('Voice select element not found');
            }

            // Clear existing options
            select.innerHTML = '<option value="">Select TTS Voice</option>';
            
            // Add each voice as an option
            edge_voices.forEach(voice => {
                const option = document.createElement('option');
                option.value = voice;
                option.textContent = voice;
                select.appendChild(option);
            });
                
        } catch (error) {
            console.error('Error loading voices:', error);
            const select = document.querySelector('select[name="ttsVoice"]');
            if (select) {
                select.innerHTML = '<option value="">Error loading voices</option>';
            }
        }
    }
    async loadVoiceModels() {
    try {
        const response = await fetch('/api/available-voices');
        if (!response.ok) throw new Error('Failed to fetch voice models');
        const data = await response.json();
        
        const modelSelect = document.getElementById('existingCharacterModel');
        data.rvc_models.forEach(modelId => {
            const option = document.createElement('option');
            option.value = modelId;
            option.textContent = modelId.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            modelSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading voice models:', error);
    }
}

setupVoiceModelHandling() {
    const typeSelect = document.getElementById('voiceModelType');
    const existingSection = document.getElementById('existingModelSection');
    const uploadSection = document.getElementById('modelUploadSection');
    const modelFile = document.getElementById('modelFile');
    const indexFile = document.getElementById('indexFile');

    if (!typeSelect || !existingSection || !uploadSection) {
        console.error('Voice model elements not found');
        return;
    }

    typeSelect.addEventListener('change', (e) => {
        existingSection.style.display = 'none';
        uploadSection.style.display = 'none';
        
        if (e.target.value === 'existing') {
            existingSection.style.display = 'block';
            document.getElementById('existingCharacterModel').required = true;
            modelFile.required = false;
            indexFile.required = false;
        } else if (e.target.value === 'upload') {
            uploadSection.style.display = 'block';
            document.getElementById('existingCharacterModel').required = false;
            modelFile.required = true;
            indexFile.required = true;
        }
    });
}

    async resizeImage(file, targetWidth = 256, targetHeight = 256, isBackground = false) {
        return new Promise((resolve) => {
            const img = new Image();
            const reader = new FileReader();

            reader.onload = function(e) {
                img.src = e.target.result;
                img.onload = function() {
                    // For backgrounds, preserve original dimensions and don't resize
                    if (isBackground) {
                        // If it's a GIF, just return the original file
                        if (file.type === 'image/gif') {
                            resolve(file);
                            return;
                        }
                        
                        const canvas = document.createElement('canvas');
                        canvas.width = img.width;
                        canvas.height = img.height;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0, img.width, img.height);
                        
                        canvas.toBlob((blob) => {
                            resolve(blob);
                        }, file.type, 0.95);
                        return;
                    }

                    // For avatars, keep the existing square resize logic
                    const canvas = document.createElement('canvas');
                    canvas.width = targetWidth;
                    canvas.height = targetHeight;
                    const ctx = canvas.getContext('2d');

                    // Fill with white background
                    ctx.fillStyle = 'white';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);

                    // Calculate scaling and position to maintain aspect ratio
                    let scale = Math.min(targetWidth / img.width, targetHeight / img.height);
                    let x = (targetWidth - img.width * scale) / 2;
                    let y = (targetHeight - img.height * scale) / 2;

                    // Draw image centered
                    ctx.drawImage(img, x, y, img.width * scale, img.height * scale);

                    // Convert to blob
                    canvas.toBlob((blob) => {
                        resolve(blob);
                    }, 'image/png', 0.95);
                };
            };
            reader.readAsDataURL(file);
        });
    }

    async handleImagePreview(event, previewId) {
        const file = event.target.files[0];
        if (!file) return;

        try {
            const isBackground = previewId === 'backgroundPreview';
            const resizedBlob = await this.resizeImage(file, 256, 256, isBackground);
            const previewUrl = URL.createObjectURL(resizedBlob);
            
            const img = document.createElement('img');
            img.src = previewUrl;
            img.className = 'preview-image';
            if (isBackground) {
                img.style.width = '100%';
                img.style.height = 'auto';
            }
            
            const previewDiv = document.getElementById(previewId);
            previewDiv.innerHTML = '';
            previewDiv.appendChild(img);

            // Store the blob for later upload
            event.target.resizedBlob = resizedBlob;
        } catch (error) {
            console.error('Error handling image preview:', error);
        }
    }
    // In characterCreation.js, modify the handleSubmit function:

async handleSubmit(event) {
    event.preventDefault();
    
    try {
        // Sanitize character name to create ID - replace all special chars with empty string
        const characterName = document.querySelector('input[name="name"]').value
            .toLowerCase()
            .replace(/[^a-z0-9]/g, ''); // Remove all non-alphanumeric characters

        const checkResponse = await fetch(`/check-character/${characterName}`);
        if (checkResponse.ok) {
            const exists = await checkResponse.json();
            if (exists.exists) {
                alert('A character with this name already exists. Please choose a different name.');
                return;
            }
        }
        
        // Validate required fields
        const requiredFields = ['name', 'description', 'systemPrompt', 'ttsVoice'];
        for (const field of requiredFields) {
            const value = this.form.elements[field].value.trim();
            if (!value) {
                alert(`${field.charAt(0).toUpperCase() + field.slice(1)} is required`);
                return;
            }
        }

        const avatarInput = document.querySelector('input[name="avatar"]');
        const backgroundInput = document.querySelector('input[name="background"]');
        
        if (!backgroundInput.files[0]) {
            alert('Background image/video is required');
            return;
        }

        if (!avatarInput.files[0]) {
            alert('Avatar image is required');
            return;
        }

        // Upload images first
        const avatarPath = await this.uploadImage(avatarInput, 'avatar');
        const backgroundPath = backgroundInput.files.length > 0 ? 
            await this.uploadImage(backgroundInput, 'background') : 
            null;

        const formData = new FormData(this.form);

// Process greetings first
const greetingsText = formData.get('greetings')?.trim();
const greetings = greetingsText
    ? greetingsText.split('\n')
        .map(g => g.trim())
        .filter(g => g.length > 0)
    : ["Hello!"];

const data = {
    id: characterName,
    name: formData.get('name'),
    description: formData.get('description'),
    systemPrompt: formData.get('systemPrompt'),
    ttsVoice: formData.get('ttsVoice'),
    category: formData.get('category'),
    is_private: formData.get('isPrivate') === 'on',
    tts_rate: parseInt(formData.get('ttsRate')) || 0,
    rvc_pitch: parseInt(formData.get('rvcPitch')) || 0,
    avatar: avatarPath,
    background: backgroundPath,
    greetings: greetings,  // Use the processed greetings array
    rvc_model: formData.get('voiceModelType') === 'existing' ? 
        formData.get('existingCharacterModel') : null,
    settings: {
        tts_rate: parseInt(formData.get('ttsRate')) || 0,
        rvc_pitch: parseInt(formData.get('rvcPitch')) || 0,
        rvc_model: formData.get('voiceModelType') === 'existing' ? 
            formData.get('existingCharacterModel') : null
    }
};

        // Validate the data
        const validatedData = this.validateParameters(data);

        const response = await fetch('/characters/create', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(validatedData)
        });

        if (!response.ok) {
            throw new Error('Failed to create character');
        }

        const result = await response.json();

        // Handle model upload if provided
        const modelFile = document.querySelector('input[name="modelFile"]');
        if (modelFile.files.length > 0) {
            await this.uploadModel(characterName);
        }

        alert('Character created successfully!');

        // Clear all input fields
        this.form.reset();
        avatarInput.value = '';
        backgroundInput.value = '';
        if (modelFile) modelFile.value = '';

        // Optional: Preview image resets
        const avatarPreview = document.getElementById('avatarPreview');
        const backgroundPreview = document.getElementById('backgroundPreview');
        if (avatarPreview) avatarPreview.src = '';
        if (backgroundPreview) backgroundPreview.src = '';

        // Redirect after a short delay to allow the user to see the success message
        setTimeout(() => {
            window.location.href = '/';
        }, 1500);

    } catch (error) {
        console.error('Error creating character:', error);
        alert('Error: ' + error.message);
    }
}

validateParameters(params) {
    const validated = {};
    
    // Required fields
    if (!params.name) throw new Error('Name is required');
    if (!params.description) throw new Error('Description is required');
    if (!params.systemPrompt) throw new Error('System prompt is required');
    if (!params.ttsVoice) throw new Error('TTS voice is required');
    if (!params.avatar) throw new Error('Avatar is required');
    
    // Validate numeric parameters
    if (params.temperature !== undefined) {
        validated.temperature = Math.min(Math.max(0.1, params.temperature), 2.0);
    }
    if (params.top_p !== undefined) {
        validated.top_p = Math.min(Math.max(0.1, params.top_p), 1.0);
    }
    if (params.top_k !== undefined) {
        validated.top_k = Math.min(Math.max(1, params.top_k), 100);
    }
    if (params.tts_rate !== undefined) {
        validated.tts_rate = Math.min(Math.max(-100, params.tts_rate), 100);
    }
    if (params.rvc_pitch !== undefined) {
        validated.rvc_pitch = Math.min(Math.max(-12, params.rvc_pitch), 12);
    }
    
    // Copy validated fields
    validated.id = params.id;
    validated.name = params.name;
    validated.description = params.description;
    validated.systemPrompt = params.systemPrompt;
    validated.ttsVoice = params.ttsVoice;
    validated.avatar = params.avatar;
    validated.category = params.category;
    validated.tags = params.tags || [];
    validated.is_private = params.is_private;
    validated.dateAdded = params.dateAdded;
    validated.greetings = Array.isArray(params.greetings) ? params.greetings : ["Hello!"]; // Ensure greetings is always an array
    validated.settings = params.settings;
    validated.ai_parameters = params.ai_parameters;
    validated.rvc_model = params.rvc_model;
    
    // Optional background
    if (params.background) {
        validated.background = params.background;
    }
    
    return validated;
}

    async uploadImage(inputElement, type) {
    if (!inputElement?.files[0] && !inputElement?.resizedBlob) return null;

    const formData = new FormData();
    const imageFile = inputElement.resizedBlob || inputElement.files[0];
    
    // Check file type
    const allowedTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp', 'video/mp4', 'video/webm', 'video/x-ms-wmv'];
    if (!allowedTypes.includes(imageFile.type)) {
        throw new Error('Invalid file type. Please use JPG, PNG, GIF, WEBP or video files.');
    }

    // Get character name and convert to valid ID format
    const characterId = document.querySelector('input[name="name"]').value
        .toLowerCase()
        .replace(/[^a-z0-9]/g, ''); // Removes everything except lowercase letters and numbers

    // Create a new File object with the character ID in the filename
    const fileExtension = imageFile.type.split('/')[1];
    const newFileName = type === 'avatar' 
        ? `${characterId}-avatar.${fileExtension}`
        : `background.${fileExtension}`;

    const file = new File([imageFile], newFileName, { type: imageFile.type });
    formData.append(type, file);
    formData.append('characterId', characterId);

    try {
        const endpoint = type === 'avatar' ? '/upload/avatar' : '/upload/character-background';
        console.log(`Uploading ${type} to ${endpoint}`);
        
        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('Upload error response:', errorText);
            throw new Error(errorText || `Failed to upload ${type}`);
        }
        
        const result = await response.json();
        console.log(`Successfully uploaded ${type}:`, result);
        
        // Return the relative path consistently formatted
        if (type === 'avatar') {
            return `./avatars/${characterId}-avatar.${fileExtension}`;
        } else {
            return `./characters/${characterId}/background.${fileExtension}`;
        }

    } catch (error) {
        console.error(`Error uploading ${type}:`, error);
        throw error;
    }
}





    async uploadModel(characterId) {
        const modelFile = document.querySelector('input[name="modelFile"]').files[0];
        const indexFile = document.querySelector('input[name="indexFile"]').files[0];

        if (!modelFile || !indexFile) {
            return null;
        }

        const formData = new FormData();
        formData.append('modelFile', modelFile);
        formData.append('indexFile', indexFile);
        formData.append('characterId', characterId);

        try {
            const response = await fetch('/characters/upload-model', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('Failed to upload model');
            }

            return await response.json();

        } catch (error) {
            console.error('Error uploading model:', error);
            throw error;
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    new CharacterCreator();
});
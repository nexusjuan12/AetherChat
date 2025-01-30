// imageGenerator.js

export async function generateCharacterImage(character, message, recentContext) {
    try {
        const prompt = await generateCharacterPrompt(character, message, recentContext);
        
        const response = await fetch('/api/v1/generate/image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                prompt: prompt,
                negative_prompt: "blurry, low quality, text, watermark, multiple characters, duplicate, multiple views",
                cfg_scale: 4.5,
                steps: 30,
                width: 512,
                height: 512,
                seed: -1,
                sampler_name: "DPM++ 2M SDE",
                scheduler: "Karras",
                highres_fix: {
                    upscale: 1.45,
                    denoising_strength: 0.4
                }
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || 'Failed to generate image');
        }

        const data = await response.json();
        
        if (!data.images || !data.images[0]) {
            throw new Error('No image data received');
        }

        return data.images[0];
    } catch (error) {
        console.error('Error generating character image:', error);
        return null;
    }
}

async function generateCharacterPrompt(character, message, recentContext) {
    try {
        const promptContext = `
Character: ${character.name}
Description: ${character.description || 'No description available'}
Current message: ${message}
Recent context: ${recentContext}

Create a visual description focusing on ${character.name} as the main subject, incorporating their current action or state, and the scene setting. Description:`;

        const response = await fetch('/api/v1/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
                prompt: promptContext,
                max_new_tokens: 150,
                temperature: 0.7,
                stop_sequence: ["\n", "."]
            })
        });
        
        if (!response.ok) throw new Error('Failed to generate image prompt');
        const data = await response.json();
        
        let prompt = data.results[0].text.trim();
        return `${prompt}, character portrait, ${character.name}, cinematic lighting, detailed features, expressive pose, high quality, masterpiece, best quality, highly detailed, dramatic`;
    } catch (error) {
        console.error('Error generating prompt:', error);
        return `portrait of ${character.name}, ${message.slice(0, 100)}, cinematic lighting, high quality, masterpiece`;
    }
}

export function updatePanelBackground(panel, imageData) {
    if (!panel || !imageData) return;
    
    const backgroundDiv = panel.querySelector('.panel-background');
    if (backgroundDiv) {
        // Fade out current background
        backgroundDiv.style.opacity = '0';
        
        // After fade out, update image and fade in
        setTimeout(() => {
            const imageUrl = `data:image/png;base64,${imageData}`;
            backgroundDiv.style.backgroundImage = `url('${imageUrl}')`;
            backgroundDiv.style.opacity = '0.6';
        }, 300);
    }
}

export function animateTransition(panel) {
    const background = panel.querySelector('.panel-background');
    if (background) {
        background.style.transform = 'scale(1.05)';
        setTimeout(() => {
            background.style.transform = 'scale(1)';
        }, 500);
    }
}
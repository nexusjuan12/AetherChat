class TaskQueue {
    constructor() {
        this.queue = [];
        this.isProcessing = false;
    }

    async addTask(task) {
        return new Promise((resolve, reject) => {
            this.queue.push({
                task,
                resolve,
                reject
            });

            if (!this.isProcessing) {
                this.processNext();
            }
        });
    }

    async processNext() {
        if (this.queue.length === 0) {
            this.isProcessing = false;
            return;
        }

        this.isProcessing = true;
        const { task, resolve, reject } = this.queue[0];

        try {
            const result = await task();
            resolve(result);
        } catch (error) {
            reject(error);
        } finally {
            this.queue.shift(); // Remove the completed task
            this.processNext(); // Process next task if any
        }
    }

    clear() {
        this.queue = [];
        this.isProcessing = false;
    }

    get length() {
        return this.queue.length;
    }
}

// Create a single instance for message handling
const messageQueue = new TaskQueue();

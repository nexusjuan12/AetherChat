// taskqueue.js
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
            this.queue.shift();
            this.processNext();
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

// Create and export the instance
window.messageQueue = new TaskQueue();

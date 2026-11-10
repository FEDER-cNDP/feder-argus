---
name: small-cnn-pytorch
description: Efficient PyTorch CNN training patterns for small datasets - TensorDataset, DataLoader, proper normalization, and compact CNN architectures
license: Apache-2.0
compatibility: Designed for deepagents CLI
metadata:
  author: DeepTok
  version: "1.0"
---

# Small CNN PyTorch Skill

## Description
This skill provides efficient patterns for training small Convolutional Neural Networks (CNNs) in PyTorch, specifically designed for scientific ML tasks with limited data. It covers TensorDataset usage, proper normalization strategies, efficient DataLoader configuration, and compact CNN architectures.

## When to Use
- Training CNNs on small to medium scientific datasets (hundreds to thousands of samples)
- Regression tasks from 2D image-like data (e.g., plasma flux surfaces)
- CPU-based training environments (common in research computing)
- When you need efficient, reproducible training loops

## Key Patterns

### 1. TensorDataset for Efficient Data Loading

**USE THIS PATTERN** - Convert numpy/xarray data directly to PyTorch tensors and use TensorDataset:

```python
import torch
from torch.utils.data import TensorDataset, DataLoader, random_split
import xarray as xr

# Load data from netCDF (xarray for lazy loading)
ds = xr.open_dataset('data.nc')
y = ds['target'].values  # Shape: (N,)
x = ds['input'].values   # Shape: (N, H, W)

# Convert to tensors
y_tensor = torch.tensor(y, dtype=torch.float32)
x_tensor = torch.tensor(x, dtype=torch.float32)

# Add channel dimension for Conv2d: (N, H, W) -> (N, 1, H, W)
x_tensor = torch.unsqueeze(x_tensor, 1)

# Create TensorDataset
dataset = TensorDataset(x_tensor, y_tensor)

# Split into train/validation (70/30)
train_dataset, val_dataset = random_split(dataset, [0.7, 0.3])

# Create DataLoaders with pin_memory for faster GPU transfer
train_loader = DataLoader(train_dataset, batch_size=32,
                          pin_memory=True, shuffle=True)
val_loader = DataLoader(val_dataset, batch_size=32,
                        pin_memory=True)
```

**AVOID** - Custom Dataset classes unless you need complex logic on-the-fly.

### 2. Per-Sample Normalization for 2D Arrays

Normalize each 2D array independently to [0, 1] using its own min/max:

```python
def normalize_to_range(tensor):
    """
    Normalize each 2D array to range [0, 1] using its own min/max.

    Args:
        tensor: Shape (N, H, W) where N is number of samples

    Returns:
        Normalized tensor with same shape, values in [0, 1]
    """
    normalized_list = []
    for i in range(tensor.size(0)):
        array_2d = tensor[i]
        max_val = array_2d.max()
        min_val = array_2d.min()
        range_val = max_val - min_val
        # Avoid division by zero
        if range_val > 0:
            normalized_array = (array_2d - min_val) / range_val
        else:
            normalized_array = torch.zeros_like(array_2d)
        normalized_list.append(normalized_array)

    return torch.stack(normalized_list)

# Usage
x_normalized = normalize_to_range(x_tensor)

# For targets: use z-score normalization
y_mean = y_tensor.mean()
y_std = y_tensor.std()
y_normalized = (y_tensor - y_mean) / y_std
# Save these for later denormalization of predictions
```

### 3. Compact CNN Architecture

**Small CNN Pattern** - ~2000 parameters, efficient for CPU training:

```python
import torch.nn as nn

class SmallCNN(nn.Module):
    def __init__(self, input_channels=1, output_dim=1):
        super(SmallCNN, self).__init__()
        # Conv block 1: reduces spatial dimensions
        self.conv1 = nn.Conv2d(input_channels, 5, kernel_size=5,
                               stride=2, padding=1)
        self.relu1 = nn.ReLU()
        self.pool1 = nn.MaxPool2d(kernel_size=3, stride=2)

        # Conv block 2: further reduction
        self.conv2 = nn.Conv2d(5, 15, kernel_size=5, stride=2)
        self.relu2 = nn.ReLU()
        self.pool2 = nn.MaxPool2d(kernel_size=2, stride=1)

        # Fully connected layers with dropout
        self.fc1 = nn.Linear(375, 100)  # Adjust input size based on your data
        self.relu3 = nn.ReLU()
        self.dropout1 = nn.Dropout(0.2)

        self.fc2 = nn.Linear(100, 30)
        self.relu4 = nn.ReLU()
        self.dropout2 = nn.Dropout(0.2)

        self.fc3 = nn.Linear(30, output_dim)

    def forward(self, x):
        # Input: (batch, 1, 65, 65) -> Output: (batch, 5, 31, 31)
        x = self.pool1(self.relu1(self.conv1(x)))
        # Output: (batch, 15, 6, 6)
        x = self.pool2(self.relu2(self.conv2(x)))
        # Flatten
        x = torch.flatten(x, 1)
        # FC layers
        x = self.dropout1(self.relu3(self.fc1(x)))
        x = self.dropout2(self.relu4(self.fc2(x)))
        x = self.fc3(x)
        return x
```

**Key design principles:**
- Use stride and pooling for dimensionality reduction instead of large convolutions
- Start with few filters (5, 15) - no need for 64/128 filters on small datasets
- Dropout (0.2) prevents overfitting on small data
- Keep FC layers small (100 -> 30 -> 1)

### 4. Proper Training Loop Pattern

```python
import time

def train_model(model, train_loader, val_loader, epochs, device, lr=0.001):
    model = model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    train_losses = []
    val_losses = []

    for epoch in range(epochs):
        epoch_start = time.time()

        # Training phase
        model.train()
        train_loss = 0.0
        for x_batch, y_batch in train_loader:
            x_batch = x_batch.to(device)
            y_batch = y_batch.to(device)

            # Forward pass
            predictions = model(x_batch)
            predictions = torch.squeeze(predictions, dim=1)  # Remove extra dim
            loss = loss_fn(predictions, y_batch)

            # Backward pass
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            train_loss += loss.item()

        train_loss /= len(train_loader)

        # Validation phase
        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for x_batch, y_batch in val_loader:
                x_batch = x_batch.to(device)
                y_batch = y_batch.to(device)

                predictions = model(x_batch)
                predictions = torch.squeeze(predictions, dim=1)
                loss = loss_fn(predictions, y_batch)
                val_loss += loss.item()

        val_loss /= len(val_loader)

        epoch_time = time.time() - epoch_start

        print(f'Epoch {epoch+1}/{epochs} ({epoch_time:.1f}s) - '
              f'Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}')

        train_losses.append(train_loss)
        val_losses.append(val_loss)

    return train_losses, val_losses

# Usage
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = SmallCNN()
train_losses, val_losses = train_model(model, train_loader, val_loader,
                                       epochs=5, device=device, lr=0.001)
```

### 5. Save Model and Plot Loss Curves

```python
import matplotlib.pyplot as plt

# Save model weights
torch.save(model.state_dict(), 'model_weights.pth')

# Plot loss curves
plt.figure(figsize=(10, 5))
plt.plot(train_losses, label='Training Loss', marker='o')
plt.plot(val_losses, label='Validation Loss', marker='s')
plt.xlabel('Epoch')
plt.ylabel('MSE Loss')
plt.title('Training and Validation Loss')
plt.legend()
plt.grid(True, alpha=0.3)
plt.savefig('loss_curves.png', dpi=150, bbox_inches='tight')
```

### 6. Evaluation and Visualization

```python
import numpy as np

def evaluate_model(model, test_loader, device, y_mean, y_std):
    """Evaluate model and denormalize predictions."""
    model.eval()
    predictions_list = []
    targets_list = []

    with torch.no_grad():
        for x_batch, y_batch in test_loader:
            x_batch = x_batch.to(device)
            predictions = model(x_batch)
            predictions = torch.squeeze(predictions, dim=1)

            # Denormalize: pred * std + mean
            predictions_denorm = predictions.cpu().numpy() * y_std + y_mean
            targets_denorm = y_batch.numpy() * y_std + y_mean

            predictions_list.append(predictions_denorm)
            targets_list.append(targets_denorm)

    all_predictions = np.concatenate(predictions_list)
    all_targets = np.concatenate(targets_list)

    # Calculate MSE
    mse = np.mean((all_predictions - all_targets) ** 2)
    print(f'Test MSE: {mse:.4f}')

    # Scatter plot
    plt.figure(figsize=(8, 8))
    plt.scatter(all_targets, all_predictions, alpha=0.5, s=10)
    plt.plot([all_targets.min(), all_targets.max()],
             [all_targets.min(), all_targets.max()],
             'r--', lw=2, label='Perfect Prediction')
    plt.xlabel('True Values')
    plt.ylabel('Predicted Values')
    plt.title(f'Predicted vs True (MSE: {mse:.4f})')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.axis('equal')
    plt.savefig('predictions_scatter.png', dpi=150, bbox_inches='tight')

    return all_predictions, all_targets, mse
```

## Complete Example Workflow

```python
import torch
from torch.utils.data import TensorDataset, DataLoader, random_split
import xarray as xr
import matplotlib.pyplot as plt

# 1. Load data
ds = xr.open_dataset('training_data.nc')
x = ds['psirz'].values      # Shape: (N, H, W)
y = ds['kappa'].values      # Shape: (N,)

# 2. Convert to tensors and add channel dim
x_tensor = torch.tensor(x, dtype=torch.float32)
x_tensor = torch.unsqueeze(x_tensor, 1)
y_tensor = torch.tensor(y, dtype=torch.float32)

# 3. Normalize
x_normalized = normalize_to_range(x_tensor)
y_mean, y_std = y_tensor.mean(), y_tensor.std()
y_normalized = (y_tensor - y_mean) / y_std

# 4. Create datasets
dataset = TensorDataset(x_normalized, y_normalized)
train_set, val_set = random_split(dataset, [0.7, 0.3])

train_loader = DataLoader(train_set, batch_size=32, shuffle=True, pin_memory=True)
val_loader = DataLoader(val_set, batch_size=32, pin_memory=True)

# 5. Train
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")
model = SmallCNN()
train_losses, val_losses = train_model(model, train_loader, val_loader,
                                       epochs=5, device=device)

# 6. Save
torch.save(model.state_dict(), 'small_cnn_model.pth')
```

## Best Practices

1. **Use TensorDataset** - Simple, efficient for in-memory data
2. **Enable pin_memory** - Set `pin_memory=True` in DataLoader for faster GPU transfer
3. **Per-sample normalization** - Normalize each 2D array independently, not globally
4. **Small architectures** - Start with 5-15 filters, not 64-128
5. **Save normalization params** - Keep y_mean, y_std for denormalizing predictions
6. **Use torch.no_grad()** - Wrap validation/inference in no_grad() context
7. **Set model modes** - Call `model.train()` for training, `model.eval()` for evaluation
8. **Track epoch time** - Monitor training time per epoch for performance

## Common Hyperparameters for Small CNNs

| Parameter | Recommended Range | Default |
|-----------|-------------------|---------|
| batch_size | 16-64 | 32 |
| learning_rate | 0.0001 - 0.01 | 0.001 |
| epochs | 5-50 | 10 |
| conv1 filters | 4-8 | 5 |
| conv2 filters | 10-20 | 15 |
| dropout | 0.1-0.3 | 0.2 |

## Troubleshooting

**High training loss:** Check normalization - inputs should be in [0,1], targets z-scored

**Overfitting:** Increase dropout, reduce model size, add more data augmentation

**Slow training:** Use smaller batch size, ensure pin_memory=True, consider fewer epochs

**NaN loss:** Learning rate too high, or division by zero in normalization

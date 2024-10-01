# -*- coding: utf-8 -*-
"""Unet_segmentation_breast_cancer.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1HoxMWWvemT0rN3qko0U2ij7PHUtjGy8G
"""

import tifffile
from skimage import io
from PIL import Image
import cv2
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
import pandas as pd

import torch
from torch import nn
import torch.nn.functional as F

from glob import glob
import os.path as osp
import numpy as np
import random
from tqdm import tqdm

from sklearn.model_selection import train_test_split

from google.colab import drive
drive.mount('/content/drive')

BASE_PATH='/content/drive/MyDrive/dataset_histo'
IMAGES_PATH = osp.join(BASE_PATH, 'images')
LABELS_PATH = osp.join(BASE_PATH, 'masks')

imgs_paths = glob(osp.join(IMAGES_PATH,'*jpg'))

print(len(imgs_paths))

masks_paths = [osp.join(LABELS_PATH, i.rsplit("/",1)[-1].split("_ccd")[0]) for i in imgs_paths]



print(len(masks_paths))

print(f"Number of images found: {len(imgs_paths)}")
print(f"Number of masks found: {len(masks_paths)}")

def get_tiff_image(path, normalized=True, resize=(512, 512)):
    image = io.imread(path)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image = cv2.resize(image, resize)
    if normalized:
        return (image / 255.0).astype(np.float32)
    return image.astype(np.float32)

def get_image(path, normalize=True, resize=(512, 512)):
    image = io.imread(path)
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    image = cv2.resize(image, resize)
    if normalize:
        return (image / 255.0).astype(np.float32)
    return image.astype(np.float32)

class BCDataset(torch.utils.data.Dataset):

    def __init__(self, img_mask_tuples):
        self.img_mask_tuples = img_mask_tuples

    def __len__(self,):
        return len(self.img_mask_tuples)

    def __getitem__(self, idx):

        img_path, mask_path = self.img_mask_tuples[idx]

        image = get_tiff_image(img_path)
        mask = get_tiff_image(mask_path, normalized=False)
        mask[mask > 0] = 1

        return image,mask

img_mask_tuples = list(zip(imgs_paths, masks_paths))

random.shuffle(img_mask_tuples)

train_tuples, test_tuples = train_test_split(img_mask_tuples)



train_dataset = BCDataset(train_tuples)
test_dataset = BCDataset(test_tuples)

train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=8, shuffle=True, num_workers=4)
test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=8, shuffle=False, num_workers=4)

import torch.nn.functional as F
class DoubleConv(nn.Module):


    def __init__(self, in_channels, out_channels, mid_channels=None):
        super().__init__()
        if not mid_channels:
            mid_channels = out_channels
        self.double_conv = nn.Sequential(
            nn.Conv2d(in_channels, mid_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(mid_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(mid_channels, out_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True)
        )
    def forward(self, x):
        return self.double_conv(x)
class Down(nn.Module):


    def __init__(self, in_channels, out_channels):
        super().__init__()
        self.maxpool_conv = nn.Sequential(
            nn.MaxPool2d(2),
            DoubleConv(in_channels, out_channels)
        )

    def forward(self, x):
        return self.maxpool_conv(x)
class Up(nn.Module):


    def __init__(self, in_channels, out_channels, bilinear=True):
        super().__init__()


        if bilinear:
            self.up = nn.Upsample(scale_factor=2, mode='bilinear', align_corners=True)
            self.conv = DoubleConv(in_channels, out_channels, in_channels // 2)
        else:
            self.up = nn.ConvTranspose2d(in_channels , in_channels // 2, kernel_size=2, stride=2)
            self.conv = DoubleConv(in_channels, out_channels)


    def forward(self, x1, x2):
        x1 = self.up(x1)
        # input is CHW
        diffY = x2.size()[2] - x1.size()[2]
        diffX = x2.size()[3] - x1.size()[3]

        x1 = F.pad(x1, [diffX // 2, diffX - diffX // 2,
                        diffY // 2, diffY - diffY // 2])

        x = torch.cat([x2, x1], dim=1)
        return self.conv(x)
class OutConv(nn.Module):
    def __init__(self, in_channels, out_channels):
        super(OutConv, self).__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size=1)

    def forward(self, x):
        return self.conv(x)
class UNet(nn.Module):
    def __init__(self, n_channels, n_classes, bilinear=True):
        super(UNet, self).__init__()
        self.n_channels = n_channels
        self.n_classes = n_classes
        self.bilinear = bilinear

        self.inc = DoubleConv(n_channels, 64)
        self.down1 = Down(64, 128)
        self.down2 = Down(128, 256)
        self.down3 = Down(256, 512)
        factor = 2 if bilinear else 1
        self.down4 = Down(512, 1024 // factor)
        self.up1 = Up(1024, 512 // factor, bilinear)
        self.up2 = Up(512, 256 // factor, bilinear)
        self.up3 = Up(256, 128 // factor, bilinear)
        self.up4 = Up(128, 64, bilinear)
        self.outc = OutConv(64, n_classes)
    def forward(self, x):
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)
        x = self.up1(x5, x4)
        x = self.up2(x, x3)
        x = self.up3(x, x2)
        x = self.up4(x, x1)
        logits = self.outc(x)
        return logits

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

model = UNet(n_channels=3, n_classes=1)
model.to(device);



criterion = nn.BCEWithLogitsLoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.001)


def dice_loss(inputs, target):
    inputs = torch.sigmoid(inputs)
    smooth = 1.
    iflat = inputs.contiguous().view(-1)
    tflat = target.contiguous().view(-1)
    intersection = (iflat * tflat).sum()
    loss = 1 - ((2. * intersection + smooth) / (iflat.sum() + tflat.sum() + smooth))
    return loss

import torch
from tqdm import tqdm
import os

checkpoint_dir = './checkpoints'
os.makedirs(checkpoint_dir, exist_ok=True)

best_accuracy = 0.0


def save_checkpoint(model, optimizer, epoch, loss, accuracy, checkpoint_dir):
    checkpoint_path = os.path.join(checkpoint_dir, f'checkpoint_epoch_{epoch}_acc_{accuracy:.4f}.pth')
    torch.save({
        'epoch': epoch,
        'model_state_dict': model.state_dict(),
        'optimizer_state_dict': optimizer.state_dict(),
        'loss': loss,
        'accuracy': accuracy
    }, checkpoint_path)
    print(f'Checkpoint saved at {checkpoint_path}')


def load_checkpoint(model, optimizer, checkpoint_dir, device):
    latest_checkpoint = max([f for f in os.listdir(checkpoint_dir) if f.endswith('.pth')], key=lambda x: int(x.split('_')[2]), default=None)
    if latest_checkpoint:
        checkpoint_path = os.path.join(checkpoint_dir, latest_checkpoint)
        checkpoint = torch.load(checkpoint_path, map_location=device)
        model.load_state_dict(checkpoint['model_state_dict'])
        optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        start_epoch = checkpoint['epoch'] + 1
        loss = checkpoint['loss']
        accuracy = checkpoint['accuracy']
        print(f'Resuming from checkpoint {checkpoint_path}, epoch {start_epoch} with accuracy {accuracy:.4f}')
        return start_epoch, loss, accuracy
    return 0, None, 0.0


def calculate_accuracy(output, labels):
    preds = torch.sigmoid(output) > 0.5
    correct = preds.eq(labels).sum().item()
    total = labels.numel()
    accuracy = correct / total
    return accuracy


start_epoch, _, best_accuracy = load_checkpoint(model, optimizer, checkpoint_dir, device)

for epoch in range(start_epoch, 10):
    epoch_loss = 0
    total_accuracy = 0

    for batch_idx, (images, labels) in enumerate(tqdm(train_loader, desc=f'Epoch {epoch + 1}/10', leave=False)):
        images = images.to(device)
        labels = labels.to(device)


        images = images.permute(0, 3, 2, 1).float()
        labels = labels.permute(0, 3, 2, 1).float()
        labels = labels.sum(1, keepdim=True).bool().float()


        output = model(images)


        loss = criterion(output, labels)
        epoch_loss += loss.item()


        accuracy = calculate_accuracy(output, labels)
        total_accuracy += accuracy


        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        if batch_idx % 10 == 0:
            print(f'Batch {batch_idx}, Loss: {loss.item():.4f}, Accuracy: {accuracy:.4f}')


    avg_accuracy = total_accuracy / len(train_loader)


    if avg_accuracy > best_accuracy:
        best_accuracy = avg_accuracy
        save_checkpoint(model, optimizer, epoch, epoch_loss / len(train_loader), avg_accuracy, checkpoint_dir)

    print(f'Epoch {epoch + 1} completed. Average Loss: {epoch_loss / len(train_loader):.4f}, Average Accuracy: {avg_accuracy:.4f}')

import matplotlib.pyplot as plt

def calculate_dice_coefficient(pred, target):
    pred = pred > 0.5
    target = target.bool()

    smooth = 1e-6
    intersection = (pred & target).sum().float()
    return (2. * intersection + smooth) / (pred.sum().float() + target.sum().float() + smooth)

import torch
import matplotlib.pyplot as plt

def visualize_predictions(test_loader, model, device, num_images=5):
    model.eval()
    with torch.no_grad():
        for i, (images, masks) in enumerate(test_loader):
            images = images.to(device)
            masks = masks.to(device)

            images = images.permute(0, 3, 1, 2)

            outputs = model(images)

            preds = torch.sigmoid(outputs)

            preds = (preds > 0.5).float()


            for j in range(min(num_images, len(images))):


                image = images[j].cpu().permute(1, 2, 0).numpy()
                image = (image - image.min()) / (image.max() - image.min())

                mask = masks[j].cpu().squeeze().numpy()
                mask = (mask - mask.min()) / (mask.max() - mask.min())

                pred = preds[j].cpu().squeeze().numpy()
                pred = (pred - pred.min()) / (pred.max() - pred.min())

                plt.figure(figsize=(10, 3))


                plt.subplot(1, 3, 1)
                plt.imshow(image)
                plt.title('Input Image')
                plt.axis('off')

                # Ground Truth Mask
                plt.subplot(1, 3, 2)
                plt.imshow(mask, cmap='gray')
                plt.title('Ground Truth Mask')
                plt.axis('off')

                # Predicted Mask
                plt.subplot(1, 3, 3)
                plt.imshow(pred, cmap='gray')
                plt.title('Predicted Mask')
                plt.axis('off')

                plt.tight_layout()
                plt.show()

            if i >= (num_images // 8):
                break


visualize_predictions(test_loader, model, device)

images = images.permute(0, 3, 1, 2).to(device)

import torch

def calculate_dice(output, labels, smooth=1e-6):
    """
    Calculate Dice coefficient for binary segmentation tasks.
    Dice coefficient = 2 * (intersection of pred and label) / (sum of pred and label)
    """
    if labels.shape[-1] == 3:
        labels = labels[:, :, :, 0]

    output = (torch.sigmoid(output) > 0.5).float()
    output = output.squeeze(1)


    intersection = (output.bool() & labels.bool()).float().sum((1, 2))
    union = output.float().sum((1, 2)) + labels.float().sum((1, 2))

    dice = (2.0 * intersection + smooth) / (union + smooth)
    return dice.mean().item()

def calculate_accuracy(output, labels):

    if labels.shape[-1] == 3:
        labels = labels[:, :, :, 0]

    # Remove extra channel from output if it exists
    if output.shape[1] == 1:
        output = output.squeeze(1)


    preds = (torch.sigmoid(output) > 0.5).float()


    correct = preds.eq(labels).sum().item()
    total = labels.numel()

    accuracy = correct / total
    return accuracy

def calculate_test_accuracy(test_loader, model, device):
    model.eval()
    correct_pixels = 0
    total_pixels = 0
    dice_score = 0

    with torch.no_grad():
        for i, (images, labels) in enumerate(test_loader):

            images = images.permute(0, 3, 1, 2).to(device)
            labels = labels.to(device)


            outputs = model(images)


            accuracy = calculate_accuracy(outputs, labels)


            dice_coefficient = calculate_dice(outputs, labels)


            correct_pixels += accuracy * labels.numel()
            total_pixels += labels.numel()
            dice_score += dice_coefficient

    avg_accuracy = correct_pixels / total_pixels
    avg_dice = dice_score / len(test_loader)


    print(f"Test Accuracy: {avg_accuracy:.4f}")
    print(f"Average Dice Coefficient: {avg_dice:.4f}")

    return avg_accuracy, avg_dice

test_accuracy, avg_dice_coefficient = calculate_test_accuracy(test_loader, model, device)

import torch
import torchvision.transforms as transforms


# Step 1: Define the model architecture
model = UNet(n_channels=3, n_classes=1)  # Instantiate your model

# Step 2: Load the saved model checkpoint
checkpoint = torch.load('/content/checkpoints/checkpoint_epoch_9_acc_0.9222.pth')
model.load_state_dict(checkpoint['model_state_dict'])  # Load model parameters
model.eval()
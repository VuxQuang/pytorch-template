import numpy as np
import cv2
import torch
from pathlib2 import Path
from torch.utils.data import Dataset,DataLoader,WeightedRandomSampler
from src.utils.temporal_transforms import *
from PIL import Image
import torchvision.transforms as transforms
import os
from src.utils import *
import random


class SpacialTransform(Dataset):
    def __init__(self,
                 output_size=(224, 224),
                 augument = None):
        self.output_size = output_size
        self.augument = augument
        self.transform_list = []
      
        if self.augument:
            if self.augument.get('color') is not None:
                self.transform_list.append(
                    transforms.ColorJitter(
                        *augument['color']
                    )
                )
        self.transform_list.append(transforms.ToTensor())
        self.transform = transforms.Compose(
            self.transform_list
        )
    def reset(self):
        if self.augument:
            if self.augument.get("h_flip") is  not None:
                self.h_flip = random.random() < self.augument.get("h_flip")
            if self.augument.get("rotation") is not None:   
                self.rotate_angle = random.uniform(-self.augument['rotation'],
                                                   self.augument['rotation'])   
    def image_augument(self,
                       image:np.array):
        
        image = Image.fromarray(image)
        
        if self.augument and self.h_flip:
            image = image.transpose(Image.FLIP_LEFT_RIGHT)
        if self.augument and self.rotate_angle is not None:
            image = image.rotate(self.rotate_angle)
        return image
    def transform_fn(self, image_nps):
        self.reset()
        image_PILs = []
        for image_np in image_nps:
                image = cv2.resize(cv2.cvtColor(image_np.astype('uint8'),
                                                 cv2.COLOR_BGR2RGB),
                                    self.output_size)
                image_PIL = self.image_augument(image)
                image_PIL = self.transform(image_PIL)
                image_PILs.append(image_PIL)
        return torch.stack(image_PILs)


class VideoFloderDataset(Dataset):
    """Face Landmarks dataset."""

    def __init__(self, 
                 root_dir,
                 sample_type="num",
                 out_frame_num=32,
                 save_class_name = None,
                 augument = None):
        """
        Args:
            root_dir (string): Directory with all the video.
        """
        self.root_dir = Path(root_dir)
        self.sub_dirs = [i for i in self.root_dir.iterdir() if i.is_dir() and not i.stem.startswith('.')]
        self.class_names = [i.stem for i in self.sub_dirs]
        self.labels = []
        self.datas = []
        self.spacial_transform = SpacialTransform(augument=augument)
        self.temporal_transform = TemporalRandomCrop(out_frame_num)
        self.sample_type = sample_type
        self.class_weights = []
        logger.info("init data set")
        for label,sub_dir in enumerate(self.sub_dirs):
                contents = [i for i in sub_dir.iterdir() if i.is_file() and not i.stem.startswith('.')]
                if len(contents)==0:
                    self.class_weights.append(0)
                else:
                    self.class_weights.append(1 / len(contents))
                if contents:
                    temp_rgb = [i for i in contents ]
                    self.labels.extend([label]*len(contents))
                    self.datas.extend(temp_rgb)
        if save_class_name:
           os.makedirs(os.path.dirname(save_class_name),exist_ok = True)
           with open(save_class_name,"w") as f:
               for class_name in self.class_names:
                   f.write(class_name+"\n")
           logger.info("save class name file at: %s",save_class_name)
    def __len__(self):
        return len(self.datas)

    def __getitem__(self, idx):
        logger.info("get item")
        rgb_data = np.float32(np.load(self.datas[idx]))
        rgb_data = self.temporal_transform(rgb_data)
        rgb_data = self.spacial_transform.transform_fn(rgb_data)
        rgb_data = rgb_data.permute(1,0,2,3).unsqueeze(0)
        return rgb_data,torch.nn.functional.one_hot(torch.tensor(self.labels[idx]), len(self.class_names)).unsqueeze(0).to(torch.float32)
def collate_fn(data):
    logger.info("collate_fn")
    features, labels  = zip(*data)
    features = torch.cat(features,dim = 0)
    labels = torch.cat(labels,dim = 0)
    return features,labels
@DATASET_REGISTRY.register()
def RGB(data_root,
        batch_size=8,
        out_frame_num=32,
        num_workers=8,
        use_sampler=False,
        save_class_name=None,
        augument=None):
        dataset = VideoFloderDataset(data_root,
                                     out_frame_num=out_frame_num,
                                     save_class_name=save_class_name,
                                     augument=augument)
  

        if use_sampler:
            sample_weights = [0] * len(dataset)
            logger.info("Init weight sampler to avoid imbalance class")

            for idx, (_, label) in enumerate(dataset):
                label = torch.argmax(label).item()
                class_weight = dataset.class_weights[label]
                sample_weights[idx] = class_weight

            sampler = WeightedRandomSampler(
                sample_weights, num_samples=len(sample_weights), replacement=True
            )

            return DataLoader(
                dataset,
                collate_fn=collate_fn,
                batch_size=batch_size,
                num_workers=num_workers,
                sampler=sampler
            )
        else:
            return DataLoader(
                dataset,
                collate_fn=collate_fn,
                batch_size=batch_size,
                num_workers=num_workers,
                shuffle=True
            )

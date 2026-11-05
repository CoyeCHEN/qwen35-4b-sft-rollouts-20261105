"""Pretokenized SFT only: preserve complete trajectories and target-aligned masks."""
import torch

def build_labels(input_ids, loss_mask):
    if input_ids.shape != loss_mask.shape:
        raise ValueError('input_ids and loss_mask must have the same shape')
    if not torch.all((loss_mask == 0) | (loss_mask == 1)):
        raise ValueError('loss_mask must be binary')
    return input_ids.masked_fill(loss_mask == 0, -100)

class MaskCollator:
    def __init__(self, pad_token_id, max_length):
        self.pad_token_id = pad_token_id
        self.max_length = max_length

    def __call__(self, rows):
        size = max(len(row['input_ids']) for row in rows)
        if size > self.max_length:
            raise ValueError(f'Complete trajectory length {size} exceeds limit {self.max_length}; truncation forbidden')
        ids = torch.full((len(rows), size), self.pad_token_id, dtype=torch.long)
        masks = torch.zeros_like(ids)
        attention = torch.zeros_like(ids)
        for i, row in enumerate(rows):
            length = len(row['input_ids'])
            if length != len(row['loss_mask']):
                raise ValueError('Mask length mismatch')
            ids[i, :length] = torch.tensor(row['input_ids'])
            masks[i, :length] = torch.tensor(row['loss_mask'])
            attention[i, :length] = 1
            if not masks[i, :length].any() or masks[i, 0] != 0:
                raise ValueError('Empty supervision or supervised initial token')
        return {'input_ids': ids, 'attention_mask': attention, 'labels': build_labels(ids, masks)}

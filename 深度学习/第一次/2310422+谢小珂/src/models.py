import torch
import torch.nn as nn
import torch.nn.functional as F


class OriginalCNN(nn.Module):
    """ CIFAR-10 原始 CNN 结构。"""
    def __init__(self, num_classes=10):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 6, kernel_size=5)
        self.pool = nn.MaxPool2d(kernel_size=2, stride=2)
        self.conv2 = nn.Conv2d(6, 16, kernel_size=5)
        self.fc1 = nn.Linear(16 * 5 * 5, 120)
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, num_classes)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = torch.flatten(x, 1)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return self.fc3(x)


def conv3x3(in_channels, out_channels, stride=1, groups=1):
    return nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1, groups=groups, bias=False)


def conv1x1(in_channels, out_channels, stride=1):
    return nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride, bias=False)


class ConvBNReLU(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size=3, stride=1, padding=1):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, out_channels, kernel_size=kernel_size, stride=stride, padding=padding, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class BasicBlock(nn.Module):
    """ResNet 基本残差块：输出为 F(x)+shortcut(x)。"""
    def __init__(self, in_channels, out_channels, stride=1, dropout=0.0):
        super().__init__()
        self.residual = nn.Sequential(
            conv3x3(in_channels, out_channels, stride),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
            nn.Dropout2d(dropout) if dropout > 0 else nn.Identity(),
            conv3x3(out_channels, out_channels),
            nn.BatchNorm2d(out_channels),
        )
        self.shortcut = nn.Identity()
        if stride != 1 or in_channels != out_channels:
            self.shortcut = nn.Sequential(conv1x1(in_channels, out_channels, stride), nn.BatchNorm2d(out_channels))
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        return self.relu(self.residual(x) + self.shortcut(x))


class MicroResNet(nn.Module):
    """面向 CIFAR-10 的微型 ResNet"""
    def __init__(self, num_classes=10, widths=(64, 128, 256), blocks=(2, 2, 2)):
        super().__init__()
        self.stem = nn.Sequential(conv3x3(3, widths[0]), nn.BatchNorm2d(widths[0]), nn.ReLU(inplace=True))
        self.stage1 = self._make_stage(widths[0], widths[0], blocks[0], stride=1)
        self.stage2 = self._make_stage(widths[0], widths[1], blocks[1], stride=2)
        self.stage3 = self._make_stage(widths[1], widths[2], blocks[2], stride=2)
        self.pool = nn.AdaptiveAvgPool2d((1, 1))
        self.dropout = nn.Dropout(p=0.25)
        self.fc = nn.Linear(widths[2], num_classes)

    def _make_stage(self, in_channels, out_channels, num_blocks, stride):
        layers = [BasicBlock(in_channels, out_channels, stride)]
        layers += [BasicBlock(out_channels, out_channels) for _ in range(1, num_blocks)]
        return nn.Sequential(*layers)

    def forward(self, x):
        x = self.stem(x)
        x = self.stage1(x)
        x = self.stage2(x)
        x = self.stage3(x)
        x = self.pool(x)
        x = torch.flatten(x, 1)
        return self.fc(self.dropout(x))


class DenseLayer(nn.Module):
    """DenseNet 层：每层输出与输入拼接，实现特征复用。"""
    def __init__(self, in_channels, growth_rate=24, bottleneck_factor=4, drop_rate=0.0):
        super().__init__()
        mid_channels = bottleneck_factor * growth_rate
        self.layer = nn.Sequential(
            nn.BatchNorm2d(in_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(in_channels, mid_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(mid_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(mid_channels, growth_rate, kernel_size=3, padding=1, bias=False),
        )
        self.drop_rate = drop_rate

    def forward(self, x):
        new_features = self.layer(x)
        if self.drop_rate > 0:
            new_features = F.dropout(new_features, p=self.drop_rate, training=self.training)
        return torch.cat([x, new_features], dim=1)


class DenseBlock(nn.Module):
    def __init__(self, in_channels, num_layers=6, growth_rate=24, drop_rate=0.0):
        super().__init__()
        channels = in_channels
        layers = []
        for _ in range(num_layers):
            layers.append(DenseLayer(channels, growth_rate=growth_rate, drop_rate=drop_rate))
            channels += growth_rate
        self.block = nn.Sequential(*layers)
        self.out_channels = channels

    def forward(self, x):
        return self.block(x)


class TransitionLayer(nn.Module):
    def __init__(self, in_channels, compression=0.5):
        super().__init__()
        out_channels = int(in_channels * compression)
        self.out_channels = out_channels
        self.transition = nn.Sequential(
            nn.BatchNorm2d(in_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
            nn.AvgPool2d(kernel_size=2, stride=2),
        )

    def forward(self, x):
        return self.transition(x)


class MicroDenseNet(nn.Module):
    """微型 DenseNet：DenseBlock + Transition，参数效率高。"""
    def __init__(self, num_classes=10, growth_rate=24, layers=(6, 8, 8), drop_rate=0.05):
        super().__init__()
        channels = 48
        self.stem = nn.Sequential(conv3x3(3, channels), nn.BatchNorm2d(channels), nn.ReLU(inplace=True))
        self.block1 = DenseBlock(channels, layers[0], growth_rate, drop_rate)
        self.trans1 = TransitionLayer(self.block1.out_channels, compression=0.5)
        self.block2 = DenseBlock(self.trans1.out_channels, layers[1], growth_rate, drop_rate)
        self.trans2 = TransitionLayer(self.block2.out_channels, compression=0.5)
        self.block3 = DenseBlock(self.trans2.out_channels, layers[2], growth_rate, drop_rate)
        channels = self.block3.out_channels
        self.final = nn.Sequential(nn.BatchNorm2d(channels), nn.ReLU(inplace=True), nn.AdaptiveAvgPool2d((1, 1)))
        self.dropout = nn.Dropout(p=0.20)
        self.fc = nn.Linear(channels, num_classes)

    def forward(self, x):
        x = self.stem(x)
        x = self.trans1(self.block1(x))
        x = self.trans2(self.block2(x))
        x = self.block3(x)
        x = self.final(x)
        x = torch.flatten(x, 1)
        return self.fc(self.dropout(x))


class DepthwiseSeparableConv(nn.Module):
    """MobileNet 的 Depthwise Conv + Pointwise Conv。"""
    def __init__(self, in_channels, out_channels, stride=1):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_channels, in_channels, kernel_size=3, stride=stride, padding=1, groups=in_channels, bias=False),
            nn.BatchNorm2d(in_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class MicroMobileNet(nn.Module):
    """带 depthwise separable convolution 的微型 MobileNet。"""
    def __init__(self, num_classes=10, width_mult=1.0):
        super().__init__()
        def c(ch):
            return max(8, int(ch * width_mult))
        self.features = nn.Sequential(
            ConvBNReLU(3, c(32), 3, 1, 1),
            DepthwiseSeparableConv(c(32), c(64), stride=1),
            DepthwiseSeparableConv(c(64), c(128), stride=2),
            DepthwiseSeparableConv(c(128), c(128), stride=1),
            DepthwiseSeparableConv(c(128), c(256), stride=2),
            DepthwiseSeparableConv(c(256), c(256), stride=1),
            DepthwiseSeparableConv(c(256), c(512), stride=2),
            DepthwiseSeparableConv(c(512), c(512), stride=1),
            DepthwiseSeparableConv(c(512), c(512), stride=1),
        )
        self.pool = nn.AdaptiveAvgPool2d((1, 1))
        self.dropout = nn.Dropout(p=0.20)
        self.fc = nn.Linear(c(512), num_classes)

    def forward(self, x):
        x = self.features(x)
        x = self.pool(x)
        x = torch.flatten(x, 1)
        return self.fc(self.dropout(x))


class Res2Block(nn.Module):
    """简化 Res2Net block：在 block 内部用 scale 分组构造多尺度特征。"""
    def __init__(self, in_channels, out_channels, stride=1, scale=4):
        super().__init__()
        assert out_channels % scale == 0
        self.scale = scale
        self.width = out_channels // scale
        self.conv1 = conv1x1(in_channels, out_channels, stride=stride)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.convs = nn.ModuleList([conv3x3(self.width, self.width) for _ in range(scale - 1)])
        self.bns = nn.ModuleList([nn.BatchNorm2d(self.width) for _ in range(scale - 1)])
        self.conv3 = conv1x1(out_channels, out_channels)
        self.bn3 = nn.BatchNorm2d(out_channels)
        self.shortcut = nn.Identity()
        if stride != 1 or in_channels != out_channels:
            self.shortcut = nn.Sequential(conv1x1(in_channels, out_channels, stride=stride), nn.BatchNorm2d(out_channels))
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        identity = self.shortcut(x)
        out = self.relu(self.bn1(self.conv1(x)))
        xs = torch.chunk(out, self.scale, dim=1)
        ys = [xs[0]]
        for i in range(1, self.scale):
            y = xs[i] if i == 1 else xs[i] + ys[-1]
            y = self.relu(self.bns[i - 1](self.convs[i - 1](y)))
            ys.append(y)
        out = torch.cat(ys, dim=1)
        out = self.bn3(self.conv3(out))
        return self.relu(out + identity)


class MicroRes2Net(nn.Module):
    """扩展模型：比 ResNet 增加 block 内多尺度表达"""
    def __init__(self, num_classes=10, widths=(64, 128, 256), blocks=(2, 2, 2), scale=4):
        super().__init__()
        self.stem = nn.Sequential(conv3x3(3, widths[0]), nn.BatchNorm2d(widths[0]), nn.ReLU(inplace=True))
        self.stage1 = self._make_stage(widths[0], widths[0], blocks[0], stride=1, scale=scale)
        self.stage2 = self._make_stage(widths[0], widths[1], blocks[1], stride=2, scale=scale)
        self.stage3 = self._make_stage(widths[1], widths[2], blocks[2], stride=2, scale=scale)
        self.pool = nn.AdaptiveAvgPool2d((1, 1))
        self.dropout = nn.Dropout(p=0.25)
        self.fc = nn.Linear(widths[2], num_classes)

    def _make_stage(self, in_channels, out_channels, num_blocks, stride, scale):
        layers = [Res2Block(in_channels, out_channels, stride=stride, scale=scale)]
        layers += [Res2Block(out_channels, out_channels, stride=1, scale=scale) for _ in range(1, num_blocks)]
        return nn.Sequential(*layers)

    def forward(self, x):
        x = self.stem(x)
        x = self.stage1(x)
        x = self.stage2(x)
        x = self.stage3(x)
        x = self.pool(x)
        x = torch.flatten(x, 1)
        return self.fc(self.dropout(x))


def get_model(model_name, num_classes=10):
    name = model_name.lower()
    if name in ["original", "cnn", "originalcnn"]:
        return OriginalCNN(num_classes=num_classes)
    if name in ["resnet", "microresnet"]:
        return MicroResNet(num_classes=num_classes)
    if name in ["densenet", "microdensenet"]:
        return MicroDenseNet(num_classes=num_classes)
    if name in ["mobilenet", "micromobilenet"]:
        return MicroMobileNet(num_classes=num_classes)
    if name in ["res2net", "microres2net"]:
        return MicroRes2Net(num_classes=num_classes)
    raise ValueError(f"Unknown model name: {model_name}")

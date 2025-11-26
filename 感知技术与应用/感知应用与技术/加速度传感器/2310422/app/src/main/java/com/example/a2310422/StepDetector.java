package com.example.a2310422;

import android.util.Log;

public class StepDetector {
    private static final float ACCEL_THRESHOLD = 10.0f; // 步伐检测阈值
    private static final int STEP_DELAY_MS = 300; // 最小步伐间隔(毫秒)

    private long lastStepTime = 0;
    public int stepCount = 0;
    private float[] lastValues = new float[3];
    private float[] currentValues = new float[3];
    private float[] gravity = new float[3];

    private static final float ALPHA = 0.8f; // 低通滤波系数

    // 低通滤波
    private float[] lowPass(float[] input, float[] output) {
        if (input == null) {
            Log.d("aaa","input空");
            return input;
        }
        if (output == null) {
            Log.d("aaa","output空");
            return input;
        }
        Log.d("aaa",Integer.toString(input.length));
        Log.d("aaa",Integer.toString(output.length));
        for (int i = 0; i < 3; i++) {
            output[i] = output[i] + ALPHA * (input[i] - output[i]);
            Log.d("aaa",Float.toString(input[i]));
            Log.d("aaa",Float.toString(input[i]));
        }
        return output;
    }

    // 处理加速度数据
    public void processAccel(float[] values, long timestamp) {
        // 1. 应用低通滤波分离重力
        gravity = lowPass(values, gravity);

        // 2. 获取线性加速度(去除重力)
        float x = values[0] - gravity[0];
        float y = values[1] - gravity[1];
        float z = values[2] - gravity[2];

        // 3. 计算加速度矢量幅度
        float accel = (float) Math.sqrt(x*x + y*y + z*z);

        // 4. 保存最近两次采样值用于波峰检测
        System.arraycopy(currentValues, 0, lastValues, 0, currentValues.length);
        currentValues[0] = x;
        currentValues[1] = y;
        currentValues[2] = z;

        // 5. 步伐检测逻辑
        detectStep(accel, timestamp);
    }

    private void detectStep(float accel, long timestamp) {
        // 计算加速度变化率
        float delta = Math.abs(accel - 9.8f);

        // 波峰检测条件
        boolean isPeak = delta > ACCEL_THRESHOLD;
        boolean isTimeValid = (timestamp - lastStepTime) > STEP_DELAY_MS;

        if (isPeak && isTimeValid) {
            lastStepTime = timestamp;
            stepCount++;
            onStepDetected(stepCount); // 回调步伐检测
        }
    }

    public interface StepListener {
        void onStep(int count);
    }

    private StepListener stepListener;

    public void setStepListener(StepListener listener) {
        this.stepListener = listener;
    }

    private void onStepDetected(int count) {
        if (stepListener != null) {
            stepListener.onStep(count);
        }
    }
}
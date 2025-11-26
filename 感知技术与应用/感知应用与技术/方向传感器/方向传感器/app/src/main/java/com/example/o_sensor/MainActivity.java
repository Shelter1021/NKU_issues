package com.example.o_sensor;
import android.app.Activity;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.os.Bundle;
import android.view.animation.Animation;
import android.view.animation.RotateAnimation;
import android.widget.ImageView;
import android.widget.TextView;

public class MainActivity extends Activity implements SensorEventListener{
    public TextView textView1;
    public TextView textView2;
    public TextView textView3;
    public TextView textView4;
    private float previousAzimuth = 0;
    ImageView image;  //指南针图片
    float currentDegree = 0f; //指南针图片转过的角度

    SensorManager mSensorManager; //管理器

    /** Called when the activity is first created. */
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.main);
        textView1=findViewById(R.id.TextView1);
        textView2=findViewById(R.id.TextView2);
        textView3=findViewById(R.id.TextView3);
        textView4=findViewById(R.id.TextView4);
        image = (ImageView)findViewById(R.id.znzImage);
        mSensorManager = (SensorManager)getSystemService(SENSOR_SERVICE); //获取管理服务
    }

    @Override
    protected void onResume(){
        super.onResume();
        //注册监听器
        mSensorManager.registerListener(this
                , mSensorManager.getDefaultSensor(Sensor.TYPE_ORIENTATION), SensorManager.SENSOR_DELAY_GAME);
    }

    //取消注册
    @Override
    protected void onPause(){
        mSensorManager.unregisterListener(this);
        super.onPause();

    }

    @Override
    protected void onStop(){
        mSensorManager.unregisterListener(this);
        super.onStop();

    }

    //传感器值改变
    @Override
    public void onAccuracyChanged(Sensor sensor, int accuracy) {
        // TODO Auto-generated method stub


    }
    //精度改变
    @Override
    public void onSensorChanged(SensorEvent event) {
        // TODO Auto-generated method stub
        //获取触发event的传感器类型
        int sensorType = event.sensor.getType();

        switch(sensorType){
            case Sensor.TYPE_ORIENTATION:
                textView1.setText("x方向的方向值(方位角）"+Float.toString(event.values[0]));
                textView2.setText("y方向的方向值(俯仰角)"+Float.toString(event.values[1]));
                textView3.setText("z方向的方向值(翻滚角)"+Float.toString(event.values[2]));
                float azimuth = event.values[0]; // 方位角（0°~359°）
                checkStraightWalking(azimuth,textView4);
                previousAzimuth = azimuth;
                float degree = event.values[0]; //获取z转过的角度
                //穿件旋转动画
                RotateAnimation ra = new RotateAnimation(currentDegree,-degree,Animation.RELATIVE_TO_SELF,0.5f
                        ,Animation.RELATIVE_TO_SELF,0.5f);
                ra.setDuration(100);//动画持续时间
                image.startAnimation(ra);
                currentDegree = -degree;
                break;

        }
    }

    private void checkStraightWalking(float azimuth,TextView textView) {
        float AZIMUTH_THRESHOLD = 1.0f;
        float delta = Math.abs(azimuth - previousAzimuth);
        delta = (delta > 180) ? 360 - delta : delta; // 确保差值在 0°~180° 之间

        if (delta < AZIMUTH_THRESHOLD) {
            textView.setText("当前直线行走");
        } else {
            textView.setText("当前非直线行走");
        }
    }
}

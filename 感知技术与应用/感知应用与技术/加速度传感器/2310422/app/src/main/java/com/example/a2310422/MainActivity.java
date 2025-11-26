package com.example.a2310422;

import static java.lang.Math.abs;
import static java.lang.Math.sqrt;

import android.app.Activity;
import android.hardware.SensorListener;
import android.hardware.SensorManager;
import android.os.Bundle;
import android.widget.TextView;

public class MainActivity extends Activity {

    TextView myTextView1;//x方向的加速度
    TextView myTextView2;//y方向的加速度
    TextView myTextView3;//z方向的加速度
    TextView myTextView4;
    TextView myTextView5;
    SensorManager mySensorManager;//SensorManager对象引用
    StepDetector stepDetector = new StepDetector();
    //SensorManagerSimulator mySensorManager;//声明SensorManagerSimulator对象,调试时用
    @Override
    public void onCreate(Bundle savedInstanceState) {//重写onCreate方法
        super.onCreate(savedInstanceState);
        setContentView(R.layout.main);//设置当前的用户界面
        myTextView1 = (TextView) findViewById(R.id.myTextView1);//得到myTextView1的引用
        myTextView2 = (TextView) findViewById(R.id.myTextView2);//得到myTextView2的引用
        myTextView3 = (TextView) findViewById(R.id.myTextView3);//得到myTextView3的引用
        myTextView4 = (TextView) findViewById(R.id.myTextView4);//得到myTextView4的引用
        myTextView5 = (TextView) findViewById(R.id.myTextView5);//得到myTextView5的引用


        mySensorManager = (SensorManager)getSystemService(SENSOR_SERVICE);//获得SensorManager
        //调试时用
        //mySensorManager = SensorManagerSimulator.getSystemService(this, SENSOR_SERVICE);
        //mySensorManager.connectSimulator();				//与Simulator服务器连接
    }

    private SensorListener mySensorListener = new SensorListener() {
        @Override
        public void onAccuracyChanged(int sensor, int accuracy) {
        }    //重写onAccuracyChanged方法

        @Override
        public void onSensorChanged(int sensor, float[] values) {        //重写onSensorChanged方法
            if (sensor == SensorManager.SENSOR_ACCELEROMETER) {//只检查加速度的变化

                stepDetector.processAccel(values, System.currentTimeMillis());

                myTextView1.setText("x方向上的加速度为：" + values[0]);    //将提取的x数据显示到TextView
                myTextView2.setText("y方向上的加速度为：" + values[1]);    //将提取的y数据显示到TextView
                myTextView3.setText("z方向上的加速度为：" + values[2]);    //将提取的x数据显示到TextView
                myTextView5.setText("当前步数为"+Integer.toString(stepDetector.stepCount));
                float x = values[0], y = values[1], z = values[2];
                float _3Da=(float) sqrt(x*x+y*y+z*z);//欧几里得距离算加速度
                if(abs(_3Da-9.8)<1.0f)//-9.8是因为地球的重力
                {
                    myTextView4.setText("当前状态判断：静止");
                }
               else
                {
                    myTextView4.setText("当前状态判断：移动");
                }

            }
        }
    };


        @Override
        protected void onResume() {//重写的onResume方法
            mySensorManager.registerListener(//注册监听
                    mySensorListener, //监听器SensorListener对象
                    SensorManager.SENSOR_ACCELEROMETER,//传感器的类型为加速度
                    SensorManager.SENSOR_DELAY_UI//传感器事件传递的频度
            );
            super.onResume();
        }

}


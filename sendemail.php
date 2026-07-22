<!DOCTYPE html>
<html lang="en">

<head>
  <meta charset="utf-8">
  <meta content="width=device-width, initial-scale=1.0" name="viewport">

  <title>qPTM | Email</title>
  <meta content="" name="descriptison">
  <meta content="" name="keywords">

  <!-- Favicons -->
  <link href="assets/img/favicon.png" rel="icon">
  <link href="assets/img/apple-touch-icon.png" rel="apple-touch-icon">

  <!-- Google Fonts -->
  <link href="https://fonts.googleapis.com/css?family=Open+Sans:300,300i,400,400i,600,600i,700,700i|Raleway:300,300i,400,400i,500,500i,600,600i,700,700i|Poppins:300,300i,400,400i,500,500i,600,600i,700,700i" rel="stylesheet">

  <!-- Vendor CSS Files -->
  <link href="assets/vendor/bootstrap/css/bootstrap.min.css" rel="stylesheet">
  <link href="assets/vendor/icofont/icofont.min.css" rel="stylesheet">
  <link href="assets/vendor/boxicons/css/boxicons.min.css" rel="stylesheet">
  <link href="assets/vendor/animate.css/animate.min.css" rel="stylesheet">
  <link href="assets/vendor/remixicon/remixicon.css" rel="stylesheet">
  <link href="assets/vendor/owl.carousel/assets/owl.carousel.min.css" rel="stylesheet">
  <link href="assets/vendor/venobox/venobox.css" rel="stylesheet">
  <link href="assets/vendor/aos/aos.css" rel="stylesheet">

  <!-- Template Main CSS File -->
  <link href="assets/css/style.css" rel="stylesheet">
</head>

<body>

  <?php require('header.php') ?>

  <!-- ======= Main Section ======= -->
  <section id="main" class="d-flex justify-cntent-center align-items-center">
    <div class="container" id="about">

		<div class="card">
			<div class="card-header"><h5 class="font-weight-bold">Download</h5></div>
		  <?php
        if(!isset($_COOKIE["valid"])){
          echo "<div class='card-body alert-danger'>Permission denid!</div>";
        }
        elseif($_COOKIE["valid"] != $_POST["msg"]){
          echo "<div class='card-body alert-danger'>Permission denid!</div>";
        }
        elseif(isset($_POST["dataset"])){
          require("./resource/email.php");
          $code = new code();
          $dataset = $_POST["dataset"];
          $title  = $_POST["title"];
          $firstname = $_POST["firstname"];
          $lastname = $_POST["lastname"];
          $affiliation = $_POST["affiliation"];
          $country = $_POST["country"];
          $email = $_POST["email"];
          file_put_contents("download_".$dataset."_list.txt", "\r\n".date('Ymd H:i:s',time())."\t$dataset\t$title\t$firstname\t$lastname\t$affiliation\t$country\t$email\r\n", FILE_APPEND);

          $filenamea = "All data in ".$dataset;
          $filea = $dataset."_all_data.zip";
          if($dataset=='qPTM'){
            //$emailcontent = "Dear $title $firstname $lastname,\n$affiliation\n$country\n\nThanks for your interest in our study, please download the $dataset dataset with the following link(s):\n\n$filenamea:\nhttp://qptm.omicsbio.info/getfile.php?id=".$code->encrypt("CUCKOO", $email)."&code=".$code->encrypt($email, $filea)."\n\nYours sincerely,\nZexian Liu Ph.D.  Associate Professor,\nSun Yat-sen University Cancer Center\n\nBuilding 2#20F, 651 Dongfeng East Road, \nGuangzhou 510060, P. R. China\nTel/Fax: +86-20-87342025\nPersonal website: http://lzx.cool";
            $emailcontent = "Dear $title $firstname $lastname,<br>$affiliation<br>$country<br><br>Thanks for your interest in our study, please download the $dataset dataset with the following link(s):<br><br>$filenamea:<br>http://qptm.omicsbio.info/getfile.php?id=".$code->encrypt("CUCKOO", $email)."&code=".$code->encrypt($email, $filea)."<br><br>Yours sincerely,<br>Professor, Ze-xian Liu<br>Sun Yat-sen University Cancer Center<br><br>Building 2#20F, 651 Dongfeng East Road, <br>Guangzhou 510060, P. R. China<br>Tel/Fax: +86-20-87342025<br>Personal website: http://lzx.cool";
          }
          $mail = new MySendMail();
          $mail->setServer("smtp.qq.com", "lzxlab@foxmail.com", "wdjawtlobnppeacc", 465, true);//设置smtp服务器，到服务器的SSL连接
          $mail->setFrom("lzxlab@foxmail.com");//发件人
          $mail->setReceiver($email); //收件人
          $mail->setCc("hujm1@sysucc.org.cn"); //抄送
          //$mail->setBcc("XXXXX"); //设置秘密抄送，多个秘密抄送，调用多次
          $mail->setMail("Download dataset of ".$dataset, $emailcontent) ;//设置邮件主题、内容
          //$mail->addAttachment("XXXX"); //添加附件，多个附件，调用多次
          //发送邮件
          if($mail->sendMail()){
            echo "<div class='card-body alert-success'>Send email successfully!</div>";
            echo "<div class='card-body'>The download link was sent to your email address of <a href='mailto:{$email}'>{$email}</a>, please check it, thanks.</div>";
          }
          else{
            $errorMsg = $mail->error();
            // 如果错误信息包含"221 Bye"，说明邮件其实已经发送成功
            if(strpos($errorMsg, '221 Bye') !== false) {
                echo "<div class='card-body alert-success'>Send email successfully!</div>";
                echo "<div class='card-body'>The download link was sent to your email address of <a href='mailto:{$email}'>{$email}</a>, please check it, thanks.</div>";
            } else {
                echo "<div class='card-body alert-danger'>Failed to send email! Error: {$errorMsg}</div>";
                echo "<div class='card-body'>Sorry, due to unknown problem, we failed to send the email. Please <a href='about.php' class='text-danger font-weight-bold'>contact us</a> to request the dataset.<br><br>We are really sorry for this.<br><br>The LZX Lab</div>";
            }
          }
        }
        else{
          header(sprintf("Location: %s", "./download.html"));
        }
      ?>

		</div>
      
    </div>
  </section><!-- End Main -->

  <?php require('footer.php') ?>

  <a href="#" class="back-to-top"><i class="ri-arrow-up-line"></i></a>
  <div id="preloader"></div>

  <!-- Vendor JS Files -->
  <script src="assets/vendor/jquery/jquery.min.js"></script>
  <script src="assets/vendor/bootstrap/js/bootstrap.bundle.min.js"></script>
  <script src="assets/vendor/jquery.easing/jquery.easing.min.js"></script>
  <script src="assets/vendor/php-email-form/validate.js"></script>
  <script src="assets/vendor/owl.carousel/owl.carousel.min.js"></script>
  <script src="assets/vendor/venobox/venobox.min.js"></script>
  <script src="assets/vendor/isotope-layout/isotope.pkgd.min.js"></script>
  <script src="assets/vendor/aos/aos.js"></script>


  <!-- Template Main JS File -->
  <script src="assets/js/main.js"></script>
  <script src="assets/js/mine.js"></script>

</body>

</html>
### Code deployment
New code is automatically packaged and deployed to Breez's S3 bucket for public consumption.


### Create S3 bucket 
```
aws s3api create-bucket --bucket breez-nodeless-payment --acl public-read
aws s3api delete-public-access-block --bucket breez-nodeless-payment
aws s3api put-bucket-policy  --bucket breez-nodeless-payment --policy '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::breez-nodeless-payment/*"
    }
  ]
}'
```

### Create user for github actions upload
```
aws iam create-user --user-name github-actions-user
aws iam put-user-policy --user-name github-actions-user --policy-name S3UploadPolicy --policy-document file://github-actions-policy.json
aws iam create-access-key --user-name github-actions-user
```